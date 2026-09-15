local healer_model = models.healer.root
local healer_animations = animations.healer
local knight_model = models.knight.root
local knight_animations = animations.knight

local locomotion = {
    hover = healer_animations.healer_hover_idle,
    forward = healer_animations.healer_fly_forward,
    backward = healer_animations.healer_fly_backward,
    left = healer_animations.healer_fly_left,
    right = healer_animations.healer_fly_right,
    falling = healer_animations.healer_fall
}

local movement_overrides = {
    locomotion.forward,
    locomotion.backward,
    locomotion.left,
    locomotion.right,
    locomotion.falling
}

local ability_animations = {
    healer_animations.healer_bolt_cast,
    healer_animations.healer_cloud_cast,
    healer_animations.healer_flight_resume
}

for _, animation in pairs(locomotion) do
    animation:setPriority(1):setBlend(1)
end
for _, animation in ipairs(movement_overrides) do
    animation:setOverride(true)
end
healer_animations.healer_flight_resume:setPriority(5):setBlend(1):setOverride(true)
healer_animations.healer_bolt_cast:setPriority(10):setBlend(1)
healer_animations.healer_cloud_cast:setPriority(10):setBlend(1)

local knight_locomotion = {
    idle = knight_animations.knight_idle,
    walk = knight_animations.knight_walk,
    run = knight_animations.knight_run
}

local knight_ability_animations = {
    knight_animations.knight_jump,
    knight_animations.knight_fall,
    knight_animations.knight_land,
    knight_animations.knight_dash,
    knight_animations.knight_slide,
    knight_animations.knight_double_jump,
    knight_animations.knight_slam_start,
    knight_animations.knight_slam_fall,
    knight_animations.knight_slam_land
}

for _, animation in pairs(knight_locomotion) do
    animation:setPriority(1):setBlend(1)
end
knight_animations.knight_fall:setPriority(3):setBlend(1):setOverride(true)
knight_animations.knight_jump:setPriority(4):setBlend(1):setOverride(true)
knight_animations.knight_land:setPriority(4):setBlend(1):setOverride(true)
knight_animations.knight_dash:setPriority(10):setBlend(1):setOverride(true)
knight_animations.knight_slide:setPriority(10):setBlend(1):setOverride(true)
knight_animations.knight_double_jump:setPriority(10):setBlend(1):setOverride(true)
knight_animations.knight_slam_start:setPriority(12):setBlend(1):setOverride(true)
knight_animations.knight_slam_fall:setPriority(12):setBlend(1):setOverride(true)
knight_animations.knight_slam_land:setPriority(12):setBlend(1):setOverride(true)

local current_locomotion = nil
local was_falling = false
local next_bolt_tick = 0
local next_cloud_tick = 0
local current_knight_locomotion = nil
local knight_was_active = false
local knight_was_grounded = true
local knight_was_sprinting = false
local knight_slam_active = false
local knight_slam_started_tick = 0
local next_dash_tick = 0
local next_slam_tick = 0

local function healer_is_active()
    local team = player:getTeamInfo()
    return team ~= nil and team.name == "mtc_healer"
end

local function knight_is_active()
    local team = player:getTeamInfo()
    return team ~= nil and team.name == "mtc_knight"
end

local function stop_healer_animations()
    for _, animation in pairs(locomotion) do
        animation:stop()
    end
    for _, animation in ipairs(ability_animations) do
        animation:stop()
    end
    current_locomotion = nil
    was_falling = false
end

local function set_locomotion(state)
    for name, animation in pairs(locomotion) do
        animation:setPlaying(name == state)
    end
    current_locomotion = state
end

local function movement_state()
    local velocity = player:getVelocity()
    if velocity.y < -0.12 then
        return "falling"
    end

    local horizontal_squared = velocity.x * velocity.x + velocity.z * velocity.z
    if horizontal_squared < 0.0004 then
        return "hover"
    end

    local yaw = math.rad(player:getBodyYaw())
    local forward_x = -math.sin(yaw)
    local forward_z = math.cos(yaw)
    local right_x = math.cos(yaw)
    local right_z = math.sin(yaw)
    local forward_amount = velocity.x * forward_x + velocity.z * forward_z
    local right_amount = velocity.x * right_x + velocity.z * right_z

    if math.abs(forward_amount) >= math.abs(right_amount) then
        return forward_amount >= 0 and "forward" or "backward"
    end
    return right_amount >= 0 and "right" or "left"
end

local function stop_knight_animations()
    for _, animation in pairs(knight_locomotion) do
        animation:stop()
    end
    for _, animation in ipairs(knight_ability_animations) do
        animation:stop()
    end
    current_knight_locomotion = nil
    knight_slam_active = false
end

local function set_knight_locomotion(state)
    for name, animation in pairs(knight_locomotion) do
        animation:setPlaying(state ~= nil and name == state)
    end
    current_knight_locomotion = state
end

local function knight_ground_state()
    local velocity = player:getVelocity()
    local horizontal_squared = velocity.x * velocity.x + velocity.z * velocity.z
    if horizontal_squared < 0.0004 then
        return "idle"
    end
    return player:isSprinting() and "run" or "walk"
end

function pings.magic_classes_knight_action(kind)
    if not knight_is_active() then
        return
    end
    if kind == "dash" then
        knight_animations.knight_dash:restart()
    elseif kind == "slide" then
        knight_animations.knight_slide:restart()
    elseif kind == "double_jump" then
        knight_animations.knight_double_jump:restart()
    elseif kind == "slam" then
        knight_slam_active = true
        knight_slam_started_tick = world.getTime()
        knight_animations.knight_slam_fall:stop()
        knight_animations.knight_slam_land:stop()
        knight_animations.knight_slam_start:restart()
    end
end

function pings.magic_classes_healer_cast(kind)
    if not healer_is_active() then
        return
    end
    if kind == "bolt" then
        healer_animations.healer_bolt_cast:restart()
    elseif kind == "cloud" then
        healer_animations.healer_cloud_cast:restart()
    end
end

local primary = keybinds:fromVanilla("key.origins.primary_active")
local secondary = keybinds:fromVanilla("key.origins.secondary_active")
local jump = keybinds:fromVanilla("key.jump")
local sneak = keybinds:fromVanilla("key.sneak")

function primary.press()
    if not host:isHost() then
        return
    end
    local now = world.getTime()
    if healer_is_active() and now >= next_bolt_tick then
        next_bolt_tick = now + 60
        pings.magic_classes_healer_cast("bolt")
    elseif knight_is_active() and now >= next_dash_tick then
        next_dash_tick = now + 8
        pings.magic_classes_knight_action("dash")
    end
end

function secondary.press()
    if not host:isHost() then
        return
    end
    local now = world.getTime()
    if healer_is_active() and now >= next_cloud_tick then
        next_cloud_tick = now + 160
        pings.magic_classes_healer_cast("cloud")
    elseif knight_is_active() and not player:isOnGround() and now >= next_slam_tick then
        next_slam_tick = now + 5
        pings.magic_classes_knight_action("slam")
    end
end

function jump.press()
    if host:isHost() and knight_is_active() and not player:isOnGround() then
        pings.magic_classes_knight_action("double_jump")
    end
end

function sneak.press()
    if host:isHost() and knight_is_active() and player:isOnGround()
            and (player:isSprinting() or knight_was_sprinting) then
        pings.magic_classes_knight_action("slide")
    end
end

function events.entity_init()
    healer_model:setVisible(false)
    knight_model:setVisible(false)
    knight_was_grounded = player:isOnGround()
end

function events.tick()
    local healer_active = healer_is_active()
    local knight_active = knight_is_active()
    local active = healer_active or knight_active
    healer_model:setVisible(healer_active)
    knight_model:setVisible(knight_active)
    vanilla_model.PLAYER:setVisible(not active)
    vanilla_model.ARMOR:setVisible(not active)
    vanilla_model.CAPE:setVisible(not active)

    if not healer_active then
        if current_locomotion ~= nil then
            stop_healer_animations()
        end
    else
        local state = movement_state()
        local falling = state == "falling"
        if was_falling and not falling then
            healer_animations.healer_flight_resume:restart()
        end
        was_falling = falling
        set_locomotion(state)
    end

    if not knight_active then
        if knight_was_active then
            stop_knight_animations()
        end
        knight_was_active = false
        knight_was_grounded = player:isOnGround()
        knight_was_sprinting = false
        return
    end

    knight_was_active = true
    local grounded = player:isOnGround()
    local velocity = player:getVelocity()

    if knight_slam_active then
        set_knight_locomotion(nil)
        knight_animations.knight_fall:stop()
        if grounded and world.getTime() > knight_slam_started_tick then
            knight_animations.knight_slam_fall:stop()
            knight_animations.knight_slam_land:restart()
            knight_slam_active = false
        elseif velocity.y < -0.05 and not knight_animations.knight_slam_start:isPlaying() then
            knight_animations.knight_slam_fall:setPlaying(true)
        end
    elseif grounded then
        knight_animations.knight_fall:stop()
        set_knight_locomotion(knight_ground_state())
        if not knight_was_grounded then
            knight_animations.knight_land:restart()
        end
    else
        set_knight_locomotion(nil)
        knight_animations.knight_fall:setPlaying(velocity.y < -0.05)
        if knight_was_grounded and velocity.y > 0.02 then
            knight_animations.knight_jump:restart()
        end
    end

    knight_was_grounded = grounded
    knight_was_sprinting = player:isSprinting()
end
