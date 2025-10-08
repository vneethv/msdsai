import os
from kaggle.api.kaggle_api_extended import KaggleApi

os.environ['KAGGLE_USERNAME'] = 'vneethv'
os.environ['KAGGLE_KEY'] = 'xxx' #Removed

api = KaggleApi()
api.authenticate()

airline_dataset = 'kursatdinc/airline-passangers'
path = './datasets'

os.makedirs(path, exist_ok=True)

api.dataset_download_files(airline_dataset, path=path, unzip=True)

print(f"Airline dataset at: {path}")

