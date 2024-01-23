## Import packages ##
import hytools as ht
import matplotlib.pyplot as plt
import matplotlib.colors as clr
import numpy as np
import requests
import sklearn
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import kneed
from kneed import KneeLocator
import scipy.spatial
from scipy.spatial import ConvexHull
import subprocess
from urllib.request import urlretrieve
import multiprocessing as mp
import os, glob
import csv
import rasterio
from osgeo import gdal
import rioxarray as rxr
import xarray as xr
import earthpy as et
import earthpy.spatial as es
import earthpy.plot as ep
import copy
import re
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from shapely.geometry import box
import geopandas as gpd
import pandas as pd
from fiona.crs import from_epsg
import pycrs
import csv
from csv import writer
# Import functions defined in S01_specdiv_functions.py
from S01_specdiv_functions import * # add scripts folder to python path manager
from window_calcs import *

# Set directories
Data_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/02_processed'
Out_Dir = '/home/ec2-user/BioSCape_across_scales/03_output'
bucket_name = 'bioscape.gra'
s3 = boto3.client('s3')

# Define S3 function
def upload_to_s3(bucket_name, file_path, s3_key):
    """
    Upload a file from an EC2 instance to Amazon S3.

    :param bucket_name: Name of the S3 bucket
    :param file_path: Local path to the file on the EC2 instance
    :param s3_key: Destination key in the S3 bucket (e.g., folder/file_name.ext)
    """
    # Initialize the S3 client
    s3 = boto3.client('s3')

    try:
    # Upload the file
        s3.upload_file(file_path, bucket_name, s3_key)
        print(f'Successfully uploaded {file_path} to {bucket_name}/{s3_key}')
    except Exception as e:
        print(f"Error uploading file: {e}")

## Set global parameters ##
#window_sizes = [10, 30, 60, 120, 240, 480]   # list of window sizes to test
window_sizes = [60, 120, 240, 480, 700, 960, 1200, 1500, 2000, 2200]
#window_sizes = [10, 50, 100, 150, 200, 300, 400]   # list of window sizes to test
ndvi_threshold = 0.4 # ndvi threshold for radiometric filtering
# shade_threshold = 500 # should be low threshold across NIR region (15%)
# cloud_threshold = 1500 # should be high threshold in blue band
#bad_bands = [[300,400],[1300,1450],[1780,2000],[2450,2600]] # bands to be masked out
#sample_size = 0.1 # proportion of pixels to subsample for fitting PCA
comps = 3 # default component numbers for PCA
#nclusters = 15 # default component numbers for K-means clustering

# Loop through clipped files
file_stem = 'SRER_flightlines/Mosaic_SRER_shape_'
sites = [3,4]
for i in sites:
    clip_file = file_stem + str(i) + '.tif'
    print(clip_file)
    s3.download_file(bucket_name, clip_file, Data_Dir + '/mosaic.tif')
    file = Data_Dir + '/mosaic.tif'
    raster = rxr.open_rasterio(file, masked=True)
    print(raster)
    # Convert data array to numpy array
    veg_np = raster.to_numpy()
    shape = veg_np.shape
    print(shape)
    # Flatten features into one dimesnion
    dim1 = shape[1]
    dim2 = shape[2]
    bands = shape[0]
    X = veg_np.reshape(bands,dim1*dim2).T
    print(X.shape)
    X = X.astype('float32')
    X[np.isnan(X)] = np.nan
    x_mean = np.nanmean(X, axis=0)[np.newaxis, :]
    X_no_nan = np.nan_to_num(X, nan=0)
    #x_mean = X_no_nan.mean(axis=0)[np.newaxis, :]
    X -=x_mean
    x_std = np.nanstd(X,axis=0)[np.newaxis, :]
    X /=x_std
    # Perform initial PCA fit
    pca = PCA(n_components=comps) # set max number of components
    pca.fit(X_no_nan)
    X_no_nan[np.isnan(X_no_nan) | np.isinf(X_no_nan)] = 0
    pca_x =  pca.transform(X_no_nan)
    print(pca_x)
    pca_x = pca_x.reshape((dim1, dim2,comps))
    print(pca_x.shape)
    # paralellize calcs for different window sizes
    results_FR = {}
    local_file_path = Out_Dir + "/SRER_fric_" + str(i) + ".csv"
    window_batches = [(a, pca_x, results_FR, local_file_path) for a in np.array_split(window_sizes, cpu_count() - 1) if a.any()]
    volumes = process_map(
        window_calcs,
        window_batches,
        max_workers=cpu_count() - 1
    )
    #print(volumes)
    # open file for writing
    # local_file_path = Out_Dir + "/TEAK_fric_" + str(i) + ".csv"
    destination_s3_key = "/SRER_fric_" + str(i) + ".csv"
    #f = open(local_file_path,"w")
    # write file
    #f.write(str(volumes))
    # close file
    #f.close()
    upload_to_s3(bucket_name, local_file_path, destination_s3_key)
    print("File uploaded to S3")
    os.remove(file)
    print("Mosaic Complete - Next...")