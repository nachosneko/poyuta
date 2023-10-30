# Discord Bot

Role attribution & auto-react for seiyuudle

## Installation

Clone the repository :

```bash
git clone https://github.com/nachosneko/poyuta.git
cd poyuta
```

Create a virtual environment :

```bash
python -m venv venv
```

Load the virtual environment :

```bash
venv\Scripts\activate # Windows
source venv/bin/activate # Linux
```

Install the dependencies in the virtual environment :

```bash
pip install -r requirements.txt
```

## Configure

Copy the .env.shared file to .env.secret :

```bash
copy .env.shared .env.secret # Windows
cp .env.shared .env.secret # Linux
```

And fill the .env.secret file with your own configuration.

## Run

Run the bot :

```bash
cd bot
python bot.py
```
