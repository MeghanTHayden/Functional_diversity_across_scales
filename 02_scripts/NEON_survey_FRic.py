#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to compute functional richness and divergence for a set of moving windows across a raster.

Author: M. Hayden
Updated: May 20, 2024

User input:
1. Name of the NEON site (e.g., BART)
    
"""

# Load required libraries
import hytools as ht
import matplotlib.pyplot as plt
import matplotlib.colors as clr
import numpy as np
import requests
import sklearn
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
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
import argparse
# Import supporting functions, functions for calculating FRic and FDiv
from S01_Functions import *
from S01_Moving_Window_FRic_plot import *

# Set directories
Data_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/02_processed'
Out_Dir = '/home/ec2-user/BioSCape_across_scales/03_output'
bucket_name = 'bioscape.gra'
s3 = boto3.client('s3')

# Set global parameters #
# window_sizes = [10, 30, 60, 120]   # smaller list of window sizes to test
window_sizes = [20] # full list of window size for computations
comps = 10 # number of components for PCA

# Identify files
# List shapefiles for a site in the S3 bucket in the matching directory
dirpath = "NEON_sr_summaries/"
objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=dirpath)['Contents']
# Filter objects based on the search criteria
rasters = [obj['Key'] for obj in objects if obj['Key'].endswith('.tif')]
raster_names = set()
for i,file in enumerate(rasters):
    match = re.search(r'NEON_sr_summaries/(.*?)_(.*?).tif', file)
    if match:
        file_name = match.group(2)
        print(file_name)
        raster_names.add(file_name)
    else:
        print("Pattern not found in the URL.")
plots = list(raster_names)  # Convert set back to a list if needed
print(plots)

# Loop through plots to calculate FRic and FDiv
file_stem = "NEON_sr_summaries/Clip_"
local_file_path_fric = Out_Dir + "/fric.csv"
for i in plots:
    # Load data
    clip_file = file_stem + str(i) + '.tif' # Define file name in S3
    print(clip_file)
    # Download plot mosaic
    s3.download_file(bucket_name, clip_file, Data_Dir + '/mosaic.tif')
    file = Data_Dir + '/mosaic.tif' # Define local file name
    print("Raster loaded")
    # Open as raster
    raster = rxr.open_rasterio(file, masked=True)
    print(raster)
    # Convert data array to numpy array
    veg_np = raster.to_numpy()
    shape = veg_np.shape
    print("Raster shape:", shape)
    
    # Process for PCA
    # Flatten features into one dimesnion
    dim1 = shape[1]
    dim2 = shape[2]
    bands = shape[0]
    X = veg_np.reshape(bands,dim1*dim2).T
    print(X.shape)
    # Set no data to nan
    X = X.astype('float32')
    X[np.isnan(X)] = np.nan
    #X[X < 0] = np.nan
    X[X <= 0] = np.nan
    X = X/10000 # rescale data
    # Impute values for NAs
    imputer = SimpleImputer(missing_values=np.nan, strategy='mean')
    try:
        X_transformed = imputer.fit_transform(X)
    except ValueError as e:
        print(f"Error occurred: {e}")
        continue
    # Scale & standardize array 
    x_mean = X_transformed.mean(axis=0)[np.newaxis, :]
    print(f"Mean: {x_mean}")
    X_transformed -=x_mean
    x_std = np.nanstd(X_transformed,axis=0)[np.newaxis, :]
    print(f"Std: {x_std}")
    X_transformed /=x_std
    # Check for NaN, inf, or very large values in the array
    if not np.isfinite(X_transformed).all():
        print("Warning: X_transformed contains NaN, inf, or very large values")
    # Replace inf values with NaN (if any) and then drop rows containing NaN
    X_transformed = np.nan_to_num(X_transformed, nan=np.nan, posinf=np.nan, neginf=np.nan)
    try:
        X_transformed_2 = imputer.fit_transform(X_transformed)
    except ValueError as e:
        print(f"Error occurred: {e}")
        continue
    # Perform initial PCA fit
    print("Fitting PCA")
    pca = PCA(n_components=comps) # set max number of components
    pca.fit(X_transformed_2)
    # PCA transform
    pca_x =  pca.transform(X_transformed_2)
    pca_x = pca_x.reshape((dim1, dim2,comps))
    print("PCA shape:", pca_x.shape)
    
    # Calculate FRic on PCA across window sizes
    print("Calculating FRic")
    window_calcs(i, shape, pca_x, local_file_path_fric)

    # Remove files to clear storage
    os.remove(file)
    X = None
    X_no_nan = None
    pca_x = None
    veg_np = None
    
    print("Mosaic Complete - Next...")

destination_s3_key_fric = "NEON_sr_summaries/Fric_plots_10pcs.csv"
upload_to_s3(bucket_name, local_file_path_fric, destination_s3_key_fric)
print("FRic file uploaded to S3")
