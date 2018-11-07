#!/bin/bash
#SBATCH -N 1
#SBATCH -J diffem
#SBATCH -t 00:30:00
#SBATCH -L SCRATCH
#SBATCH -A ***REMOVED***
#SBATCH --mail-type=ALL
#SBATCH --partition=realtime
#SBATCH --mail-user=dgold@berkeley.edu
#SBATCH --image=registry.services.nersc.gov/dgold/improc:latest
#SBATCH --dependency={dlist:s}


export OMP_NUM_THREADS=1
export USE_SIMPLE_THREADED_LEVEL3=1

news=$1
ref=$2
cats=$3
obase=$4

shifter python /lensgrinder/pipeline/bin/makecoadd.py --input-frames=${news} --input-catalogs=${cats} \
               --output-basename=${obase}

srun -n 64 shifter python /lensgrinder/pipeline/bin/makesub.py --science-images=${obase}.fits \
               --templates=${ref}.fits
