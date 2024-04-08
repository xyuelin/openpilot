import os
import stat
import time
import urllib.request

from openpilot.common.params import Params

VERSION = 'v1'
REPOSITORY_URL = 'https://github.com/FrogAi/FrogPilot-Resources/releases/download'

DEFAULT_MODEL = "duck-amigo"
DEFAULT_MODEL_NAME = "Duck Amigo (Default)"
MODELS_PATH = '/data/models'

params = Params()
params_memory = Params("/dev/shm/params")

def download_model():
  model = params_memory.get("ModelToDownload", encoding='utf-8') or DEFAULT_MODEL
  model_path = os.path.join(MODELS_PATH, f"{model}.thneed")

  if not os.path.exists(os.path.dirname(model_path)):
    os.makedirs(os.path.dirname(model_path), exist_ok=True)

  for attempt in range(5):
    try:
      url = f"{REPOSITORY_URL}/{model}/{model}.thneed"
      with urllib.request.urlopen(url) as response:
        total_file_size = int(response.getheader('Content-Length'))

        if total_file_size != 0:
          with urllib.request.urlopen(url) as f, open(model_path, 'wb') as output:
            current_file_size = 0
            while True:
              chunk = f.read(8192)
              if not chunk:
                break
              output.write(chunk)
              current_file_size += len(chunk)
              progress = current_file_size / total_file_size
              params_memory.put_int("ModelDownloadProgress", int(progress * 100))
            os.fsync(output)

      downloaded_file_size = os.path.getsize(model_path)
      if downloaded_file_size == total_file_size:
        print(f"Successfully downloaded the {model} model!")
        time.sleep(1)
        params_memory.remove("ModelToDownload")
        params_memory.remove("ModelDownloadProgress")
        break
      else:
        print(f"Failed to download the {model} model on attempt {attempt + 1}. Retrying...")
        time.sleep(5)

    except Exception as e:
      print(f"Attempt {attempt + 1} failed with error: {e}. Retrying...")
      time.sleep(5)

  else:
    print(f"Failed to download the {model} model after 5 attempts. Giving up... :(")
    params_memory.remove("ModelToDownload")

  if os.path.exists(model_path) and downloaded_file_size == total_file_size:
    try:
      current_permissions = stat.S_IMODE(os.lstat(model_path).st_mode)
      os.chmod(model_path, current_permissions | stat.S_IEXEC)
    except Exception as e:
      print(f"Failed to set file permissions for {model}.thneed: {e}")

def delete_deprecated_models():
  available_models = params.get("AvailableModels", encoding='utf-8')

  if available_models:
    available_models = available_models.split(',')
    current_model = params.get("Model", encoding='utf-8')

    if current_model not in available_models:
      params.put("Model", DEFAULT_MODEL)
      params.put("ModelName", DEFAULT_MODEL_NAME)

    for model_file in os.listdir(MODELS_PATH):
      if model_file.endswith('.thneed') and model_file[:-7] not in available_models:
        os.remove(os.path.join(MODELS_PATH, model_file))

def populate_models():
  model_names_url = f"https://raw.githubusercontent.com/FrogAi/FrogPilot-Resources/master/model_names_{VERSION}.txt"

  try:
    with urllib.request.urlopen(model_names_url) as response:
      model_info = [line.decode('utf-8').strip().split(' - ') for line in response.readlines() if ' - ' in line.decode('utf-8')]

    available_models = ','.join(model[0] for model in model_info)
    available_models_names = ','.join(model[1] for model in model_info)

    params.put("AvailableModels", available_models)
    params.put("AvailableModelsNames", available_models_names)

  except Exception as e:
    print(f"Failed to update models list. Error: {e}")
