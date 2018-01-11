import logging
import os
import subprocess
from typing import List

from game import GameType
from player import Player, BotPlayer

logger = logging.getLogger(__name__)

DOCKER_STARCRAFT_NETWORK = "sc_net"


def check_docker_version():
    try:
        out = subprocess.check_output(["docker", "--version"])
    except Exception as e:
        raise Exception("An error occurred while trying to call `docker --version`,"
                        " did you install docker?")

    if not out.startswith(b"Docker version 17.09.0-ce"):
        raise Exception(
            f"Docker version does not start with 'Docker version 17.09.0-ce', found {out}")


def check_docker_can_run():
    try:
        out = subprocess.check_output(["docker", "run", "hello-world"])
    except Exception as e:
        raise Exception(
            "An error occurred while trying to call `docker run hello-world`, "
            "do you have suffiecient rights to run sudo?")

    if b"Hello" not in out:
        raise Exception(
            f"Docker did not run properly - could'nt find 'Hello' in hello-world run, found {out}")


def check_docker_has_local_net() -> bool:
    try:
        out = subprocess.check_output(
            ["docker", "network", "ls", "-f", f"name={DOCKER_STARCRAFT_NETWORK}", "-q"])
    except Exception as e:
        raise Exception(
            f"An error occurred while trying to call `docker network ls -f name={DOCKER_STARCRAFT_NETWORK} -q`")

    logger.debug(f"docker network id: {out}")
    return bool(out)


def create_local_net():
    try:
        logger.info(f"creating docker local net {DOCKER_STARCRAFT_NETWORK}")
        out = subprocess.check_output(
            ["docker", "network", "create", "--subnet=172.18.0.0/16", DOCKER_STARCRAFT_NETWORK])
    except Exception as e:
        raise Exception(
            f"An error occurred while trying to call `docker network create --subnet=172.18.0.0/16 {DOCKER_STARCRAFT_NETWORK}`")

    logger.debug(f"docker network id: {out}")


def check_docker_requirements():
    check_docker_version()
    check_docker_can_run()
    check_docker_has_local_net() or create_local_net()


BASE_VNC_PORT = 5900
APP_DIR = "/app"
LOG_DIR = f"{APP_DIR}/logs"
SC_DIR = f"{APP_DIR}/sc"
BWTA_DIR = f"{APP_DIR}/bwta"
BWAPI_DIR = f"{APP_DIR}/bwapi"
BOT_DIR = f"{APP_DIR}/bots"
MAP_DIR = f"{SC_DIR}/maps"
BWAPI_DATA_DIR = f"{SC_DIR}/bwapi-data"
BWAPI_DATA_BWTA_DIR = f"{BWAPI_DATA_DIR}/BWTA"
BWAPI_DATA_BWTA2_DIR = f"{BWAPI_DATA_DIR}/BWTA2"
BOT_DATA_SAVE_DIR = f"{BWAPI_DATA_DIR}/save"
BOT_DATA_READ_DIR = f"{BWAPI_DATA_DIR}/read"
BOT_DATA_WRITE_DIR = f"{BWAPI_DATA_DIR}/write"
BOT_DATA_AI_DIR = f"{BWAPI_DATA_DIR}/AI"
BOT_DATA_LOGS_DIR = f"{BWAPI_DATA_DIR}/logs"


def launch_image(
        # players info
        player: Player,
        nth_player: int,
        num_players: int,

        # game settings
        headless: bool,
        game_name: str,
        map_name: str,
        game_type: GameType,
        game_speed: int,

        # mount dirs
        log_dir: str,
        bot_dir: str,
        map_dir: str,
        bwapi_data_bwta_dir: str,
        bwapi_data_bwta2_dir: str,

        vnc_base_port: int,

        # docker
        docker_image: str,
        docker_opts: List[str]):
    #
    cmd = ["docker", "run",

           "-d",
           "--privileged",

           "--name", f"{game_name}_{nth_player}_{player.name.replace(' ', '_')}",

           "--volume", f"{log_dir}:{LOG_DIR}:rw",
           "--volume", f"{bot_dir}:{BOT_DIR}:ro",
           "--volume", f"{map_dir}:{MAP_DIR}:rw",
           "--volume", f"{bwapi_data_bwta_dir}:{BWAPI_DATA_BWTA_DIR}:rw",
           "--volume", f"{bwapi_data_bwta2_dir}:{BWAPI_DATA_BWTA2_DIR}:rw",

           "--net", DOCKER_STARCRAFT_NETWORK]

    if docker_opts:
        cmd += docker_opts

    if not headless:
        cmd += ["-p", f"{vnc_base_port+nth_player}:5900"]

    if isinstance(player, BotPlayer):
        bot_data_write_dir = f"{player.base_dir}/write_{game_name}_{nth_player}"
        os.makedirs(bot_data_write_dir, mode=0o777)  # todo: proper mode
        cmd += ["--volume", f"{bot_data_write_dir}:{BOT_DATA_WRITE_DIR}:rw"]

    cmd += [docker_image]

    entrypoint_cmd = []
    if isinstance(player, BotPlayer):
        entrypoint_cmd += ["/app/play_bot.sh"]
    else:
        entrypoint_cmd += ["/app/play_human.sh"]

    entrypoint_cmd += [player.name,
                       player.race.value,
                       str(nth_player),
                       str(num_players),
                       game_name,
                       f"/app/sc/maps/{map_name}",
                       game_type.value,
                       str(game_speed)]
    if isinstance(player, BotPlayer):
        entrypoint_cmd += [player.name,
                           player.bot_basefilename]

    cmd += entrypoint_cmd

    entrypoint_extra_cmd = []
    is_server = nth_player == 0

    if not headless:
        entrypoint_extra_cmd += ["--headful"]
    else:
        entrypoint_extra_cmd += ["--game", game_name,
                                 "--name", player.name,
                                 "--race", player.race.value,
                                 "--lan"]

        if is_server:
            entrypoint_extra_cmd += ["--host",
                                     "--map", f"/app/sc/maps/{map_name}"]
        else:
            entrypoint_extra_cmd += ["--join"]

    cmd += entrypoint_extra_cmd

    logger.debug(cmd)
    code = subprocess.call(cmd)

    if code == 0:
        logger.info(f"launched {player} in container {game_name}_{nth_player}_{player.name}")
    else:
        raise Exception(
            f"could not launch {player} in container {game_name}_{nth_player}_{player.name}")


def running_containers(name_prefix):
    out = subprocess.check_output(f'docker ps -f "name={name_prefix}" -q', shell=True)
    containers = [container.strip() for container in out.decode("utf-8").split("\n") if
                  container != ""]
    logger.debug(f"running containers: {containers}")
    return containers