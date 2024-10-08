#If virtual environment does not exist, construct one using pip
if [ ! -d "pathbench_env" ]; then
    python3 -m venv pathbench_env
    source pathbench_env/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source pathbench_env/bin/activate
fi

#Set slideflow backends
export SF_SLIDE_BACKEND=cucim
export SF_BACKEND=torch

#Set the config file
CONFIG_FILE=conf.yaml

#Run the program
python3 main.py --config $CONFIG_FILE