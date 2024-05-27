import pandas as pd
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html  # Импортируем dcc и html из dash
from dash.dependencies import Input, Output
import aiohttp
from aiohttp import BasicAuth
from urllib.parse import quote
from datetime import datetime, timedelta, time
import asyncio


################################################ CONFIG ################################################################
# Версия с drag-n-drop

serverip = '172.20.10.4'
GetCurrentMachineInfo_url = f'http://{serverip}:9000/MachineDashboardData/GetCurrentMachineInfo'
GetMachineList_url = f'http://{serverip}:9000/GetMachineList'
GetMachineParamList_url = f'http://{serverip}:9000/GetMachineParamList'
GetParamInMachineList_url = f'http://{serverip}:9000/ParamInMachine/GetParamInMachineList'
GetSignals_url = f"http://{serverip}:9000/Signal/GetSignals"

auth = BasicAuth('Admin', '123')
headers = {
    'accept': 'application/json',
}

# Определение размеров плиток
TILE_WIDTH = '130px'
TILE_HEIGHT = '135px'

########################################################################################################################
async def get_params(session):
    print("Fetching machine parameters...")
    async with session.get(GetMachineParamList_url, headers=headers, auth=auth) as response1:
        machineparam_list = await response1.json()

    async with session.get(GetParamInMachineList_url, headers=headers, auth=auth) as response2:
        paraminmachines_list = await response2.json()

    machineparam_dict = {item["id"]: item["name"] for item in machineparam_list}
    data = [
        {"machineID": i["machineID"], "machineParamID": i["machineParamID"], "id": i["id"],
         "name": machineparam_dict[i["machineParamID"]]}
        for i in paraminmachines_list
    ]

    result = {}
    for item in data:
        machine_id = item['machineID']
        if machine_id in result:
            result[machine_id].append(item)
        else:
            result[machine_id] = [item]

    filtered_data = {
        machine_id: [param for param in params if param['name'] in ('Feed', 'Part counter')]
        for machine_id, params in result.items() if any(param['name'] in ('Feed', 'Part counter') for param in params)
    }
    print("Fetched machine parameters successfully.")
    return filtered_data


async def fetch_data(session):
    print("Fetching machine data...")
    async with session.get(GetCurrentMachineInfo_url, headers=headers, auth=auth) as response1:
        machine_info_list = await response1.json()

    async with session.get(GetMachineList_url, headers=headers, auth=auth) as response2:
        machine_list = await response2.json()

    combined_list = []
    machine_dict = {machine['id']: machine for machine in machine_list}
    for machine_info in machine_info_list:
        machine = machine_dict.get(machine_info['machineId'])
        if machine:
            combined_entry = {
                'machineId': machine['id'],
                'machineParamColor': '#b2b2b2' if machine_info['machineParamColor'] == '#000000' else machine_info[
                    'machineParamColor'],
                'machineParamName': machine_info['machineParamName'],
                'fileUpName': machine_info['fileUpName'],
                'machineName': machine['name'],
                'machineShortName': machine['shortName'],
                'machine_url': f'https://{serverip}:8001/monitoring/realtime/machine/{machine["id"]}'
            }
            combined_list.append(combined_entry)
    print("Fetched machine data successfully.")
    return combined_list


async def GetSignals(session, machineId, date_from, date_to):
    print(f"Fetching signals for machine {machineId} from {date_from} to {date_to}...")
    maxpoints = 1
    async with session.get(
            f"{GetSignals_url}?machineId={machineId}&maxpoints={maxpoints}&from={date_from}&to={date_to}",
            headers=headers, auth=auth) as response:
        result = await response.json()
        print(f"Fetched signals for machine {machineId}.")
        return result


async def get_feed_value(session, data):
    print("Fetching feed values...")
    current_time = datetime.now()
    earlier_time = current_time - timedelta(seconds=10)
    current_time_str = quote(current_time.strftime('%Y-%m-%d %H:%M:%S'))
    earlier_time_str = quote(earlier_time.strftime('%Y-%m-%d %H:%M:%S'))

    tasks = [
        get_feed_value_for_machine(session, machine, earlier_time_str, current_time_str)
        for machine in data
    ]
    result = await asyncio.gather(*tasks)
    print("Fetched feed values successfully.")
    return result


async def get_feed_value_for_machine(session, machine, earlier_time_str, current_time_str):
    feed = "-"
    feed_id = machine.get("feed_id")
    if feed_id:
        signals = await GetSignals(session, machine["machineId"], earlier_time_str, current_time_str)
        for signal in signals:
            if signal["paramInMachineId"] == feed_id:
                feed = signal["avg"]
    machine["actual_feed"] = feed
    return machine


async def get_partcouter_value(session, data):
    print("Fetching part counter values...")
    current_time = datetime.now()
    earlier_time = datetime.combine(current_time.date(), time(8, 0))
    current_time_str = quote(current_time.strftime('%Y-%m-%d %H:%M:%S'))
    earlier_time_str = quote(earlier_time.strftime('%Y-%m-%d %H:%M:%S'))
    tasks = [
        get_partcouter_value_for_machine(session, machine, earlier_time_str, current_time_str)
        for machine in data
    ]
    result = await asyncio.gather(*tasks)
    print("Fetched part counter values successfully.")
    return result


async def get_partcouter_value_for_machine(session, machine, earlier_time_str, current_time_str):
    partcounter = "-"
    partcounter_id = machine.get("partcounter_id")
    if partcounter_id:
        signals = await GetSignals(session, machine["machineId"], earlier_time_str, current_time_str)
        for signal in signals:
            print(signal)
            try:
                if signal["paramInMachineId"] == partcounter_id:
                    partcounter = signal["sum"]
    machine["actual_partcounter"] = partcounter
    return machine


async def update_data():
    print("Updating data...")
    async with aiohttp.ClientSession() as session:
        paramsinsystem = await get_params(session)
        data = await fetch_data(session)
        data = get_paramid(data, paramsinsystem)
        data = await get_feed_value(session, data)
        data = await get_partcouter_value(session, data)
    print("Data updated successfully.")
    return data


def get_paramid(data, params):
    for machine in data:
        machine_id = machine['machineId']
        if machine_id in params:
            for param in params[machine_id]:
                if param['name'] == 'Feed':
                    machine['feed_id'] = param['id']
                if param['name'] == 'Part counter':
                    machine['partcounter_id'] = param['id']
    return data


def transform_data(data):
    return pd.DataFrame(data)


# Инициализация Dash с использованием темы Bootstrap
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div([
    html.Div([
        html.Div([
            html.Img(src='/assets/CloEE logo green _ black.svg', style={'height': '50px', 'marginRight': '20px'}),
            html.Img(src='/assets/company_logo.png', style={'height': '50px', 'marginRight': '20px'}),
            html.H1("Monitoring panel", style={'margin': '0', 'display': 'inline-block', 'verticalAlign': 'middle', 'marginRight': '20px', 'color': '2C3E50'}),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div(id='clock', style={'fontSize': '24px', 'fontWeight': 'bold', 'position': 'absolute', 'top': '5px', 'right': '5px', 'color': '2C3E50'})
    ], style={'position': 'relative', 'backgroundColor': '#ECF0F1', 'padding': '10px', 'borderBottom': '2px solid #2C3E50'}),
    dcc.Interval(id='interval-component', interval=10 * 1000, n_intervals=0),
    dcc.Interval(id='clock-interval', interval=1000, n_intervals=0),
    html.Div(id='dashboard',
             style={'display': 'grid', 'gridTemplateColumns': f'repeat(auto-fit, minmax({TILE_WIDTH}, 1fr))', 'gap': '5px',
                    'padding': '5px', 'marginTop': '20px', 'position': 'relative', 'overflow': 'visible'})
])

# Обновление дашборда каждые 10 секунд
@app.callback(Output('dashboard', 'children'), [Input('interval-component', 'n_intervals')])
def update_dashboard(n):
    print(f"Updating dashboard, interval: {n}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = loop.run_until_complete(update_data())
    df = transform_data(data)
    tiles = []
    for i, row in df.iterrows():
        color = row['machineParamColor']
        tile = html.Div([
            html.P(f"{row['machineShortName']}", style={
                'margin': '2px 0', 'fontWeight': 'bold', 'fontSize': '13px',
                'overflow': 'hidden', 'textOverflow': 'ellipsis',
                'display': '-webkit-box', 'WebkitLineClamp': '2', 'WebkitBoxOrient': 'vertical', 'whiteSpace': 'normal'}),
            html.P(f"{row['machineParamName']}", style={
                'margin': '2px 0', 'fontSize': '12px',
                'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
            html.P(f"Prog: {row['fileUpName']}", style={
                'margin': '2px 0', 'fontSize': '12px',
                'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
            html.P(f"Feed: {str(row['actual_feed'])[:7]}", style={
                'margin': '2px 0', 'fontSize': '12px',
                'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
            html.P(f"Part Counter: {str(row['actual_partcounter'])}", style={
                'margin': '2px 0', 'fontSize': '12px',
                'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'})
        ], style={
            'border': f'1px solid {color}',
            'backgroundColor': color,
            'color': '#e5e5e5',  # Цвет шрифта
            'padding': '5px',
            'boxShadow': '1px 2px 5px rgba(0,0,0,0.1)',
            'borderRadius': '5px',
            'minHeight': TILE_HEIGHT,
            'width': TILE_WIDTH,
            'position': 'relative',
            'transition': 'transform 0.3s, boxShadow 0.3s, zIndex 0.3s'
        }, className='tile', **{'data-id': i})
        # Оберните плитку элементом html.A, чтобы сделать её кликабельной
        tile_link = html.A(tile, href=row['machine_url'], target='_blank', style={'textDecoration': 'none'})
        tiles.append(tile_link)
    return tiles

# Обновление часов каждую секунду
@app.callback(Output('clock', 'children'), [Input('clock-interval', 'n_intervals')])
def update_clock(n):
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return now

# Стиль для фона страницы
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                background-color: #2C3E50;
                font-family: sans-serif;
            }
            #dashboard {
                position: relative;
                overflow: visible;
            }
            .tile {
                z-index: 1;
                transition: transform 0.3s, box-shadow 0.3s, z-index 0.3s;
            }
            .tile:hover {
                transform: scale(1.15);
                box-shadow: 3px 6px 10px rgba(0,0,0,0.2);
                z-index: 10;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script src="/assets/Sortable.min.js"></script>
        <script>
            console.log("Initializing Sortable...");
            document.addEventListener('DOMContentLoaded', function () {
                console.log("DOM fully loaded and parsed.");
                const observer = new MutationObserver(function(mutationsList, observer) {
                    for(const mutation of mutationsList) {
                        if (mutation.type === 'childList' && document.getElementById('dashboard')) {
                            console.log("Dashboard element found.");
                            observer.disconnect();
                            const dashboard = document.getElementById('dashboard');
                            new Sortable(dashboard, {
                                animation: 150,
                                onEnd: function (evt) {
                                    console.log('Element dropped', evt);
                                    console.log('Old index:', evt.oldIndex);
                                    console.log('New index:', evt.newIndex);
                                }
                            });
                            break;
                        }
                    }
                });

                observer.observe(document.body, { childList: true, subtree: true });
            });
        </script>
    </body>
</html>
'''

if __name__ == '__main__':
    app.run_server(debug=True)
