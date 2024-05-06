import datetime
import http.client
import os
import socket
import time
import urllib.error
import urllib.request

import cereal.messaging as messaging

from cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL, Priority, config_realtime_process
from openpilot.common.time import system_time_valid
from openpilot.system.hardware import HARDWARE

from openpilot.selfdrive.frogpilot.controls.frogpilot_planner import FrogPilotPlanner
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import FrogPilotFunctions
from openpilot.selfdrive.frogpilot.controls.lib.model_manager import DEFAULT_MODEL, DEFAULT_MODEL_NAME, download_model, populate_models
from openpilot.selfdrive.frogpilot.controls.lib.theme_manager import ThemeManager

WIFI = log.DeviceState.NetworkType.wifi

def automatic_update_check(params):
  update_available = params.get_bool("UpdaterFetchAvailable")
  update_ready = params.get_bool("UpdateAvailable")
  update_state = params.get("UpdaterState", encoding='utf8')

  if update_ready:
    HARDWARE.reboot()
  elif update_available:
    os.system("pkill -SIGHUP -f selfdrive.updated.updated")
  elif update_state == "idle":
    os.system("pkill -SIGUSR1 -f selfdrive.updated.updated")

def github_pinged(url="https://github.com", timeout=5):
  try:
    urllib.request.urlopen(url, timeout=timeout)
    return True
  except (urllib.error.URLError, socket.timeout, http.client.RemoteDisconnected):
    return False

def time_checks(automatic_updates, deviceState, params):
  if github_pinged():
    populate_models()

    screen_off = deviceState.screenBrightnessPercent == 0
    wifi_connection = deviceState.networkType == WIFI

    if automatic_updates and screen_off and wifi_connection:
      automatic_update_check(params)

def frogpilot_thread():
  config_realtime_process(5, Priority.CTRL_LOW)

  params = Params()
  params_memory = Params("/dev/shm/params")

  frogpilot_functions = FrogPilotFunctions()
  theme_manager = ThemeManager()

  CP = None

  automatic_updates = params.get_bool("AutomaticUpdates")
  first_run = True
  model_list_empty = params.get("AvailableModelsNames", encoding='utf-8') is None
  time_validated = system_time_valid()

  pm = messaging.PubMaster(['frogpilotPlan'])
  sm = messaging.SubMaster(['carState', 'controlsState', 'deviceState', 'frogpilotCarControl', 'frogpilotNavigation',
                            'frogpilotPlan', 'liveLocationKalman', 'longitudinalPlan', 'modelV2', 'radarState'],
                           poll='modelV2', ignore_avg_freq=['radarState'])

  while True:
    sm.update()

    deviceState = sm['deviceState']
    started = deviceState.started

    if started:
      if CP is None:
        with car.CarParams.from_bytes(params.get("CarParams", block=True)) as msg:
          CP = msg
          frogpilot_planner = FrogPilotPlanner(CP)
          frogpilot_planner.update_frogpilot_params()

      if sm.updated['modelV2']:
        frogpilot_planner.update(sm['carState'], sm['controlsState'], sm['frogpilotCarControl'], sm['frogpilotNavigation'],
                                  sm['liveLocationKalman'], sm['modelV2'], sm['radarState'])
        frogpilot_planner.publish(sm, pm)

    if params_memory.get("ModelToDownload", encoding='utf-8') is not None and github_pinged():
      download_model()

    if params_memory.get_bool("FrogPilotTogglesUpdated"):
      automatic_updates = params.get_bool("AutomaticUpdates")

      if not params.get_bool("ModelSelector"):
        params.put("Model", DEFAULT_MODEL)
        params.put("ModelName", DEFAULT_MODEL_NAME)

      if started:
        frogpilot_planner.update_frogpilot_params()
      else:
        frogpilot_functions.backup_toggles()

    if not time_validated:
      time_validated = system_time_valid()
      if not time_validated:
        continue

    if datetime.datetime.now().second == 0 or first_run or model_list_empty or params_memory.get_bool("ManualUpdateInitiated"):
      if not started or model_list_empty:
        time_checks(automatic_updates, deviceState, params)
        model_list_empty = params.get("AvailableModelsNames", encoding='utf-8') is None

      theme_manager.update_holiday()

      first_run = False

    time.sleep(DT_MDL)

def main():
  frogpilot_thread()

if __name__ == "__main__":
  main()
