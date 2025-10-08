import os
import pandas as pd
import matplotlib.pyplot as graph
from kaggle.api.kaggle_api_extended import KaggleApi


os.environ['KAGGLE_USERNAME'] = 'vneethv'
os.environ['KAGGLE_KEY'] = 'xxx' #replace

api = KaggleApi()
api.authenticate()

airline_dataset = 'kursatdinc/airline-passangers'
path = './datasets'

os.makedirs(path, exist_ok=True)

# download from kaggle

api.dataset_download_files(airline_dataset, path=path, unzip=True)

print(f"Airline dataset at: {path}")

datafile = 'airline-passengers.csv'
file_path = os.path.join(path, datafile)
df = pd.read_csv(file_path)

#shoe couple of lines

print(df.head())

#plot it

df['month'] = pd.to_datetime(df['month'])

graph.figure(figsize=(12,6))
graph.plot(df['month'], df['total_passengers'], marker='o', color='blue')
graph.title("Air Passengers (1949-1960)")
graph.xlabel("month")
graph.ylabel("No of Passengers")
graph.xticks(rotation=100)
graph.grid(True)
graph.show()

