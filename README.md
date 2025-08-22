# AiraHome-Dashboard
Simple dashboard to display data from pyairahome.
> [!WARNING]
> This project is still WIP (Work In Progress), expect bugs and issues. Please open an issue [here](https://github.com/Invy55/pyairahome/issues/new/choose) when you do.

<img width="1919" height="1412" alt="img" src="https://github.com/user-attachments/assets/df91e3ed-4785-4e67-98e0-51d50c9e1da6" />

## Getting started
__Setting up this dashboard is very straightforward. Let's get started:__

1. Clone the github repository on your machine
```bash
git clone https://github.com/Invy55/AiraHome-Dashboard.git 
```
> _You can also download the repository from github using the green button_
<br/>

2. Cd to the downloaded directory, copy and edit the env file
```bash
cd AiraHome-Dashboard
cp app/.env.sample app/.env
```
Set email and password in app/.env
<br/>
<br/>

3. Start the dashboard using docker compose
```bash
docker compose up -d
```
> _Might be docker-compose on older systems_
<br/>

4. Done!
Navigate to http://localhost:4000/d/beuirjjdi4cu8c/airahome-dashboard to check the dashboard out!
> _Change localhost to your machine ip where the dashboard is running_

##
#### Disclaimer
_This project is an independent, open-source software library developed for interacting with AiraHome heat pumps via their app gRPC APIs. It is not affiliated with, endorsed by, sponsored by, or associated with AiraHome or any of its subsidiaries, affiliates, or partners. The project is not an official product of AiraHome, and the use of this library does not imply any compatibility, support, or approval from AiraHome. All trademarks, service marks, and company names mentioned herein are the property of their respective owners. Use of this library is at your own risk, and the developers are not responsible for any damages, malfunctions, or issues arising from its use with AiraHome or other heat pump systems._