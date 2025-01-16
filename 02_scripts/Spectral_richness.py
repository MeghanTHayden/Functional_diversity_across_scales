import os
import re
import gc
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import rasterio
import rioxarray as rxr
import numpy as np
import sklearn
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler
import requests
from multiprocessing import Pool, cpu_count
from tqdm.contrib.concurrent import process_map
#from S01_Functions import *
from S01_Moving_Window_FRIC import *
#from S01_Moving_Window_FDiv import *

def identify_plots(SITECODE, s3, bucket_name):
  # List pcas for a site in the S3 bucket in the matching directory
  search_criteria = "_pca_"
  dirpath = SITECODE + "_flightlines/"
  objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=dirpath)['Contents']
  
  # Filter objects based on the search criteria
  pcas = [obj['Key'] for obj in objects if obj['Key'].endswith('.tif') and (search_criteria in obj['Key'])]
  pca_names = set()
  for i,tif in enumerate(pcas):
      match = re.search(r'(.*?)_flightlines/(.*?)_pca_(.*?).tif', tif)
      if match:
          pca_name = match.group(3)
          print(pca_name)
          pca_names.add(pca_name)
      else:
          print("Pattern not found in the URL.")
  plots = list(pca_names)  # Convert set back to a list if needed
  print(plots)
  
  return plots

def load_pca(SITECODE, plot, s3, bucket_name, Data_Dir):
  # Load data
  file_stem = SITECODE + '_flightlines/' + SITECODE + '_pca_'
  clip_file = file_stem + str(plot) + '.tif' # Define file name in S3
  print(clip_file)
  
  # Download plot mosaic
  local_file = f"{Data_Dir}/pca_{plot}.tif"
  s3.download_file(bucket_name, clip_file, local_file)
  print(f"Raster downloaded to {local_file}")
  
  # Open as raster
  raster = rxr.open_rasterio(local_file, masked=True)
  print(raster)

  # Convert to numpy array
  pca_x = raster.to_numpy()
  print("Raster shape:", pca_x.shape)
  pca_x = np.moveaxis(pca_x, 0, -1)
  print("Reformatted shape:", pca_x.shape)

  return pca_x

def randomize_pixels(pca_x):
  # Randomize pixels to remove spatial organization
  print("Randomizing pixels for null distribution...")
  shape = pca_x.shape
  dim1, dim2, ncomps = shape[0], shape[1], shape[2]
  pca_x_flat = pca_x.reshape(-1, ncomps)  # Flatten PCA array to 2D (n_pixels, n_components)
  print("Flattened shape for randomization:", pca_x_flat.shape)
  pca_x_flat_shuffled = np.random.permutation(pca_x_flat)          # Shuffle rows randomly
  pca_x_random = pca_x_flat_shuffled.reshape(dim1, dim2,ncomps)  # Reshape back to original dimensions
  print("Randomization complete. Shape:", pca_x_random.shape)

  # Verify randomization
  print(f"Original data sample: {pca_x[200:210]}")
  print(f"Randomized data sample: {pca_x_random[200:210]}")

  return pca_x_random

def calculate_fric(SITECODE, plot, pca_x, window_sizes, bucket_name, Out_Dir):
  # Calculate FRic on PCA across window sizes
  print("Calculating FRic")
  results_FR = {}
  local_file_path_fric = Out_Dir + "/" + SITECODE + "_fric_" + str(plot) + ".csv"
  window_batches = [(a, pca_x, results_FR, local_file_path_fric) for a in np.array_split(window_sizes, cpu_count() - 1) if a.any()]
  volumes = process_map(
       window_calcs,
       window_batches,
       max_workers=cpu_count() - 1
   )
  destination_s3_key_fric = "/" + SITECODE + "_specdiv_" + str(plot) + ".csv"
  s3 = boto3.client('s3')
  s3.upload_file(local_file_path_fric, bucket_name, destination_s3_key_fric)
  print("FRic file uploaded to S3")

def calculate_fric_null(SITECODE, plot, pca_x_random, window_sizes, bucket_name, Out_Dir):
  # Calculate FRic on PCA across window sizes
  print("Calculating FRic")
  results_FR_null = {}
  local_file_path_fric_null = Out_Dir + "/" + SITECODE + "_fric_null_" + str(plot) + ".csv"
  window_batches = [(a, pca_x_random, results_FR_null, local_file_path_fric_null) for a in np.array_split(window_sizes, cpu_count() - 1) if a.any()]
  volumes = process_map(
       window_calcs,
       window_batches,
       max_workers=cpu_count() - 1
   )
  destination_s3_key_fric = "/" + SITECODE + "_specdiv_null_" + str(plot) + ".csv"
  s3 = boto3.client('s3')
  s3.upload_file(local_file_path_fric_null, bucket_name, destination_s3_key_fric)
  print("Null FRic file uploaded to S3")

def process_spectral_richness(SITECODE):
  # Set directories
  Data_Dir = '/home/ec2-user/Functional_diversity_across_scales/01_data'
  Out_Dir = '/home/ec2-user/Functional_diversity_across_scales/02_output'
  bucket_name = 'bioscape.gra'
  s3 = boto3.client('s3')

  # Define window sizes
  window_sizes = [60, 90, 130, 195, 285, 420, 620, 920, 1355, 2000]

  plots = identify_plots(SITECODE, s3, bucket_name)
  for plot in plots:
    pca_x = load_pca(SITECODE, plot, s3, bucket_name, Data_Dir)
    pca_x_random = randomize_pixels(pca_x)
    calculate_fric(SITECODE, plot, pca_x, window_sizes, bucket_name, Out_Dir)
    calculate_fric_null(SITECODE, plot, pca_x_random, window_sizes, bucket_name, Out_Dir)

  print(f"Processing {SITECODE} complete")

# Example usage
if __name__ == "__main__":
    
    process_spectral_richness(SITECODE)
  
    