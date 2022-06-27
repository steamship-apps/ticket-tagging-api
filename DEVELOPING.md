# Developing

You can easily fork, customize, and republish this app with new functionality.

## Change the Handle

App handles are unique in Steamship. Think of them like you think of an NPM or Pip package name.

To customize and re-deploy this app as your own, first edit the `handle` propery of `steamship.json` to create a new handle name.

## Set up your Virtual Environment

We recommend using Python virtual environments for development.
To set one up, run the following command from this directory:

```bash
python3 -m venv .venv
```

Activate your virtual environment by running:

```bash
source .venv/bin/activate
```

Your first time, install the required dependencies with:

```bash
python -m pip install -r requirements.dev.txt
python -m pip install -r requirements.txt
```

## Develop

All the code for this app is located in the `src/api.py` file.

Think of Steamship apps as Flask-style web apps that expose functionality over HTTP. Unlike typical Flask apps, Steamship apps can use the rest of the Steamship platform to provide training, inference, and data storage with zero infrastructure wrangling on your part. 

* **During development**, Steamship's Flask-style library lets you develop and test your app as if it was a regular Python class.
* **Once deployed**, our runtime environment will map this Python class to HTTP endpoints.
* **As a client**, you can call these endpoints over raw HTTP or use the Steamship client libraries 

## Throw, Log, and Test!

The app code in this project will be executing (1) remotely, (2) automatically, and (3) potentially at high-scale. This makes it critical that you:

* Throw detailed exceptions eagerly
* Log liberally
* Write unit tests

See `TESTING.md` for details on the pre-configured testing setup.

## Deploying

To run this app on Steamship, you must first deploy it. 

See `DEPLOYING.md` for instructions.