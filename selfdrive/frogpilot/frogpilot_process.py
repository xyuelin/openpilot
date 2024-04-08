import datetime
import os
import threading
import time
import urllib.error
import urllib.request

import cereal.messaging as messaging

from cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL, Priority, config_realtime_process
from openpilot.common.time import system_time_valid
from openpilot.system.hardware import HARDWARE

from openpilot.selfdrive.frogpilot.controls.frogpilot_plannerd import FrogPilotPlannerd
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import FrogPilotFunctions
from openpilot.selfdrive.frogpilot.controls.lib.model_manager import DEFAULT_MODEL, DEFAULT_MODEL_NAME, download_model, populate_models
from openpilot.selfdrive.frogpilot.controls.lib.theme_manager import ThemeManager

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

def is_connected_to_internet(url="https://github.com", timeout=5):
  try:
    urllib.request.urlopen(url, timeout=timeout)
    return True
  except urllib.error.URLError:
    return False

def frogpilot_thread():
  config_realtime_process(5, Priority.CTRL_LOW)

  params = Params()
  params_memory = Params("/dev/shm/params")

  frogpilot_functions = FrogPilotFunctions()
  theme_manager = ThemeManager()

  CP = None

  automatic_updates = params.get_bool("AutomaticUpdates")
  first_run = True
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
          frogpilot_plannerd = FrogPilotPlannerd(CP)
          frogpilot_plannerd.update_frogpilot_params()

      if sm.updated['modelV2']:
        frogpilot_plannerd.update(sm['carState'], sm['controlsState'], sm['frogpilotCarControl'], sm['frogpilotNavigation'],
                                  sm['liveLocationKalman'], sm['modelV2'], sm['radarState'])
        frogpilot_plannerd.publish(sm, pm)

    if params_memory.get("ModelToDownload", encoding='utf-8') is not None:
      download_model()

    if params_memory.get_bool("FrogPilotTogglesUpdated"):
      automatic_updates = params.get_bool("AutomaticUpdates")

      if not params.get_bool("ModelSelector"):
        params.put("Model", DEFAULT_MODEL)
        params.put("ModelName", DEFAULT_MODEL_NAME)

      if started:
        frogpilot_plannerd.update_frogpilot_params()

      frogpilot_backup = threading.Thread(target=frogpilot_functions.backup_toggles)
      frogpilot_backup.start()

    if not time_validated:
      time_validated = system_time_valid()
      if not time_validated:
        continue

    if datetime.datetime.now().second == 0 or first_run or params_memory.get_bool("ManualUpdateInitiated"):
      populate_models()

      screen_off = deviceState.screenBrightnessPercent == 0
      internet_connection = is_connected_to_internet()

      check_update = screen_off and internet_connection and not started

      if check_update and automatic_updates:
        automatic_update_check(params)

      theme_manager.update_holiday()
      first_run = False

    time.sleep(DT_MDL)

def main():
  frogpilot_thread()

if __name__ == "__main__":
  main()
