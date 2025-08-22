from flask import Flask, request
import importlib
import pkgutil
from pyairahome import AiraHome
from dotenv import load_dotenv # type: ignore
import os
import json

# Load environment variables from .env file
load_dotenv()
username = os.getenv("AIRAHOME_USERNAME")
password = os.getenv("AIRAHOME_PASSWORD")
if not username or not password:
    raise ValueError("Please set AIRAHOME_USERNAME and AIRAHOME_PASSWORD in the .env file")

app = Flask("AiraHome API")
aira = AiraHome()
aira.login_with_credentials(username, password)

allowed_commands = {}
for command in aira.get_command_list():
    allowed_commands[command] = aira.get_command_fields(command)

@app.route("/")
def root():
    return "Bad usage! Go to /get_commands to see available commands."

@app.route("/get_commands")
def get_commands():
    return {
        "commands": list(allowed_commands.keys())
    }

@app.route("/get_command_fields/<command_name>")
def get_command_fields(command_name):
    if command_name not in allowed_commands:
        return {
            "error": "Command not found"
        }, 404
    
    fields = allowed_commands[command_name]
    return {
        "command": command_name,
        "fields": fields
    }

@app.route("/command/<command_name>")
def command(command_name):
    if command_name not in allowed_commands:
        return {
            "error": "Command not found"
        }, 404
    if not "heatpump_id" in request.args:
        return {
            "error": "heatpump_id parameter is required"
        }, 400
    
    heatpump_id = request.args.get("heatpump_id")
    fields = request.args.to_dict()
    # Remove heatpump_id from fields
    fields.pop("heatpump_id", None)

    return aira.send_command(heatpump_id, command_name, **fields) # type: ignore

@app.route("/progress/")
def progress():
    if not "command_id" in request.args:
        return {
            "error": "command_id parameter is required"
        }, 400
    command_id = request.args.get("command_id")
    print(command_id)
    def stream():
        for update in aira.stream_command_progress(command_id):
            yield f"{json.dumps(update)}\n"
    
    return stream(), 200, {"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}



if __name__ == "__main__":  
   app.run(host="0.0.0.0", port=80, debug=False)