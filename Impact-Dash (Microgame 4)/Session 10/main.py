import os
import sys

# ── Headless / Codespaces environment fixes ───────────────────────────────────
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":99"

if not os.environ.get("XDG_RUNTIME_DIR"):
    os.environ["XDG_RUNTIME_DIR"] = "/tmp/runtime-vscode"
    os.makedirs("/tmp/runtime-vscode", exist_ok=True)

os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import random
from feedback import screen_shake
from tween import ease_out, lerp

# ─────────────────────────────────────────
#  INITIALISE pygame
# ─────────────────────────────────────────
pygame.init()

# ─────────────────────────────────────────
#  SCREEN / WINDOW SETUP
# ─────────────────────────────────────────
SCREEN_WIDTH  = 640
SCREEN_HEIGHT = 480
TITLE         = "Impact Dash"

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(TITLE)

clock = pygame.time.Clock()
FPS = 60

# ─────────────────────────────────────────
#  COLOURS  (R, G, B)
# ─────────────────────────────────────────
BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
GRAY   = ( 40,  40,  40)
YELLOW = (255, 255, 0)
GREEN  = (  0, 255, 0)
RED    = (255,   0, 0)
AMBER  = (255, 180, 0)
ORANGE = (255, 100, 0)

# ─────────────────────────────────────────
#  GAME SETTINGS  (tweak these to tune difficulty)
# ─────────────────────────────────────────
PLAYER_SPEED   = 5

dash_speed     = 18
dash_cooldown  = 60
MIN_DASH       = 5      # dash length (frames) for a quick tap of SHIFT
DASH_DURATION  = 10     # dash length (frames) for a fully charged dash
MAX_CHARGE     = 25     # frames of holding SHIFT to reach full charge

START_TIME     = 30 * FPS   # starting clock
TIME_BONUS     = 3 * FPS    # seconds added per smashed target
HITSTOP_FRAMES = 4          # tiny freeze on impact for punch
MAX_TARGETS    = 8

POPUP_LIFE = 50
POPUP_RISE = 1.2

# ─────────────────────────────────────────
#  FONTS
# ─────────────────────────────────────────
font       = pygame.font.Font(None, 36)
small_font = pygame.font.Font(None, 28)
title_font = pygame.font.Font(None, 64)
popup_font = pygame.font.Font(None, 48)

title_surf   = title_font.render("Impact Dash", True, WHITE)
title_w      = title_surf.get_width()
title_dest_x = (SCREEN_WIDTH - title_w) // 2

# ─────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────
state      = "menu"
menu_anim  = 0.0
high_score = 0

player        = pygame.Rect(100, 100, 40, 40)
targets       = []
particles     = []
score_popups  = []
shake_offsets = []

dash_timer  = 0
dash_active = 0
dir_x       = 0
dir_y       = 0

charging    = False
charge_time = 0

score     = 0
wave      = 1
time_left = START_TIME
hitstop   = 0

# ── TRANSITIONS ──────────────────────────
FADE_SPEED    = 8
fade_surface  = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
fade_surface.fill(BLACK)
fade_alpha    = 255
fade_dir      = -1
pending_state = None

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def draw_grid(surface):
    for x in range(0, SCREEN_WIDTH, 40):
        pygame.draw.line(surface, GRAY, (x, 0), (x, SCREEN_HEIGHT))
    for y in range(0, SCREEN_HEIGHT, 40):
        pygame.draw.line(surface, GRAY, (0, y), (SCREEN_WIDTH, y))

def spawn_particles(x, y, color=YELLOW, amount=20, bias_x=0, bias_y=0):
    for _ in range(amount):
        particles.append({
            "pos":   [x, y],
            "vel":   [random.randint(-3, 3) + bias_x,
                      random.randint(-3, 3) + bias_y],
            "color": color,
            "life":  random.randint(20, 40)
        })

def draw_popups(surface):
    for popup in score_popups:
        alpha     = int(255 * (popup["life"] / popup["max_life"]))
        text_surf = popup_font.render(popup["value"], True, GREEN)
        tmp       = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        tmp.blit(text_surf, (0, 0))
        tmp.set_alpha(alpha)
        draw_x = int(popup["x"]) - text_surf.get_width() // 2
        draw_y = int(popup["y"])
        surface.blit(tmp, (draw_x, draw_y))

def draw_player(surface, rect, charging, charge_t):
    if not charging:
        pygame.draw.rect(surface, WHITE, rect)
        return

    t = min(charge_t / MAX_CHARGE, 1.0)
    w = int(rect.width  * lerp(1.0, 0.70, t))
    h = int(rect.height * lerp(1.0, 1.20, t))

    cx, cy   = rect.centerx, rect.centery
    squished = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surface, WHITE, squished)

def draw_centered(text, fnt, color, y):
    surf = fnt.render(text, True, color)
    screen.blit(surf, ((SCREEN_WIDTH - surf.get_width()) // 2, y))

def start_transition(target_state):
    """Begin fading to black; switch to target_state at peak."""
    global fade_dir, pending_state
    fade_dir      = +1
    pending_state = target_state

def spawn_wave(count):
    """Place `count` targets at random spots, away from the player."""
    targets.clear()
    while len(targets) < count:
        t = pygame.Rect(random.randint(20, SCREEN_WIDTH - 50),
                        random.randint(20, SCREEN_HEIGHT - 70), 30, 30)
        if not t.colliderect(player.inflate(160, 160)) and t.collidelist(targets) == -1:
            targets.append(t)

def reset_game():
    global score, wave, time_left, dash_timer, dash_active, hitstop
    global shake_offsets, charging, charge_time
    score, wave, time_left = 0, 1, START_TIME
    dash_timer = dash_active = hitstop = 0
    charging, charge_time = False, 0
    shake_offsets = []
    particles.clear()
    score_popups.clear()
    player.topleft = (100, 100)
    spawn_wave(2)

# ─────────────────────────────────────────
#  GAME LOOP
# ─────────────────────────────────────────
running = True

while running:

    # ── EVENT HANDLING ───────────────────
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

            # Only accept menu keys when fully visible (not mid-transition)
            if fade_dir == 0:
                if state == "menu" and event.key == pygame.K_SPACE:
                    start_transition("gameplay")
                elif state == "gameover" and event.key == pygame.K_r:
                    start_transition("gameplay")
                elif state == "gameover" and event.key == pygame.K_m:
                    start_transition("menu")

        # ── SHIFT RELEASED → fire the dash ──────────────────────────────
        if event.type == pygame.KEYUP:
            if event.key == pygame.K_LSHIFT and charging:
                live_keys = pygame.key.get_pressed()
                dx = (1 if live_keys[pygame.K_RIGHT] else -1 if live_keys[pygame.K_LEFT] else 0)
                dy = (1 if live_keys[pygame.K_DOWN]  else -1 if live_keys[pygame.K_UP]   else 0)
                t  = min(charge_time / MAX_CHARGE, 1.0)
                charging    = False
                charge_time = 0
                # No direction held -> cancel the charge instead of wasting the dash
                if dx or dy:
                    dir_x, dir_y = dx, dy
                    dash_timer  = dash_cooldown
                    dash_active = int(lerp(MIN_DASH, DASH_DURATION, t))  # longer charge = longer dash
                    spawn_particles(player.centerx, player.centery,
                                    color=YELLOW, amount=40,
                                    bias_x=-dir_x * 5, bias_y=-dir_y * 5)

    # ── UPDATE: FADE ─────────────────────
    fade_alpha += FADE_SPEED * fade_dir
    if fade_dir == +1 and fade_alpha >= 255:
        fade_alpha    = 255
        fade_dir      = -1
        state         = pending_state
        pending_state = None
        # Set up the new screen while it's hidden behind black
        if state == "gameplay":
            reset_game()
        elif state == "menu":
            menu_anim = 0.0
    elif fade_dir == -1 and fade_alpha <= 0:
        fade_alpha = 0
        fade_dir   = 0

    # ── UPDATE: MENU ─────────────────────
    if state == "menu":
        menu_anim = min(menu_anim + 0.02, 1.0)

    # ── UPDATE: GAMEPLAY ─────────────────
    elif state == "gameplay":

        playing = time_left > 0

        # Particles and popups keep animating even during hit-stop / time-up
        for p in particles[:]:
            p["pos"][0] += p["vel"][0]
            p["pos"][1] += p["vel"][1]
            p["life"]   -= 1
            if p["life"] <= 0:
                particles.remove(p)

        for popup in score_popups[:]:
            popup["y"]    -= POPUP_RISE
            popup["life"] -= 1
            if popup["life"] <= 0:
                score_popups.remove(popup)

        if not playing:
            charging, charge_time = False, 0

        elif hitstop > 0:
            hitstop -= 1          # brief freeze on impact

        else:
            keys = pygame.key.get_pressed()

            if keys[pygame.K_LEFT]:  player.x -= PLAYER_SPEED
            if keys[pygame.K_RIGHT]: player.x += PLAYER_SPEED
            if keys[pygame.K_UP]:    player.y -= PLAYER_SPEED
            if keys[pygame.K_DOWN]:  player.y += PLAYER_SPEED

            # Hold SHIFT to charge
            if dash_timer == 0 and keys[pygame.K_LSHIFT] and dash_active == 0:
                charging = True
                if charge_time % 4 == 0:
                    spawn_particles(player.centerx, player.centery,
                                    color=AMBER, amount=2)
                charge_time = min(charge_time + 1, MAX_CHARGE)

            if dash_active > 0:
                # Diagonal dashes are slowed so they aren't ~40% longer
                step = dash_speed if (dir_x == 0 or dir_y == 0) else int(dash_speed * 0.71)
                player.x += dir_x * step
                player.y += dir_y * step
                dash_active -= 1
                spawn_particles(player.centerx - dir_x * 15,
                                player.centery - dir_y * 15,
                                color=YELLOW, amount=6,
                                bias_x=-dir_x * 3, bias_y=-dir_y * 3)

            if dash_timer > 0:
                dash_timer -= 1

            player.clamp_ip(screen.get_rect())

            for t in targets[:]:
                if player.colliderect(t) and dash_active > 0:
                    points = 10 * wave
                    spawn_particles(t.centerx, t.centery, color=ORANGE, amount=40)
                    shake_offsets = screen_shake()
                    targets.remove(t)
                    score     += points
                    time_left += TIME_BONUS
                    hitstop    = HITSTOP_FRAMES
                    score_popups.append({
                        "value":    f"+{points}",
                        "x":        float(t.centerx),
                        "y":        float(t.centery),
                        "life":     POPUP_LIFE,
                        "max_life": POPUP_LIFE,
                    })

            # Wave cleared -> next wave, one more target, dash refreshed
            if not targets:
                wave  += 1
                score += 50
                dash_timer = 0
                spawn_wave(min(1 + wave, MAX_TARGETS))

            time_left -= 1
            if time_left <= 0:
                time_left  = 0
                high_score = max(high_score, score)
                start_transition("gameover")

    # ── RENDER: MENU ─────────────────────
    if state == "menu":
        screen.fill(BLACK)

        title_x = int(lerp(-title_w, title_dest_x, ease_out(menu_anim)))
        screen.blit(title_surf, (title_x, 150))

        if menu_anim >= 0.9:
            draw_centered("Press SPACE to start", font, (200, 200, 200), 240)
            draw_centered("Arrows: move   Hold SHIFT + direction, release to dash",
                          small_font, (140, 140, 140), 290)
            draw_centered("Longer charge = longer dash. Smash targets to beat the clock!",
                          small_font, (140, 140, 140), 315)
            if high_score:
                draw_centered(f"Best: {high_score}", small_font, AMBER, 360)

    # ── RENDER: GAMEPLAY ─────────────────
    elif state == "gameplay":
        screen.fill(BLACK)
        game_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        game_surface.fill(BLACK)
        draw_grid(game_surface)

        bar_fill  = int(200 * (1 - dash_timer / dash_cooldown)) if dash_timer > 0 else 200
        bar_color = GREEN if dash_timer == 0 else RED
        pygame.draw.rect(game_surface, GRAY,      (20, SCREEN_HEIGHT - 20, 200, 12))
        pygame.draw.rect(game_surface, bar_color, (20, SCREEN_HEIGHT - 20, bar_fill, 12))

        for p in particles:
            pygame.draw.circle(game_surface, p["color"],
                               (int(p["pos"][0]), int(p["pos"][1])), 3)

        draw_player(game_surface, player, charging, charge_time)

        for t in targets:
            pygame.draw.rect(game_surface, AMBER, t)

        draw_popups(game_surface)

        # HUD
        secs = time_left / FPS
        game_surface.blit(font.render(f"Score: {score}", True, WHITE), (20, 15))
        game_surface.blit(small_font.render(f"Wave {wave}", True, AMBER), (20, 45))
        t_surf = font.render(f"{secs:0.1f}s", True, RED if secs < 5 else WHITE)
        game_surface.blit(t_surf, (SCREEN_WIDTH - t_surf.get_width() - 20, 15))

        ox, oy = shake_offsets.pop(0) if shake_offsets else (0, 0)
        screen.blit(game_surface, (ox, oy))

    # ── RENDER: GAMEOVER ─────────────────
    elif state == "gameover":
        screen.fill((80, 0, 0))
        draw_centered("TIME'S UP!", title_font, WHITE, 130)
        draw_centered(f"Score: {score}   Wave: {wave}", font, WHITE, 210)
        draw_centered(f"Best: {high_score}", font, AMBER, 250)
        draw_centered("R: play again    M: menu", small_font, (220, 200, 200), 320)

    # ── RENDER: FADE OVERLAY ─────────────
    if fade_alpha > 0:
        fade_surface.set_alpha(fade_alpha)
        screen.blit(fade_surface, (0, 0))

    pygame.display.flip()
    clock.tick(FPS)

# ─────────────────────────────────────────
#  CLEAN UP
# ─────────────────────────────────────────
pygame.quit()
sys.exit()
