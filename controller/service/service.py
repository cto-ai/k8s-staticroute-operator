import flask
import json
import os
from flask import request, jsonify, make_response
import sqlite3
from functools import wraps

dbfile = "/db/router.db"
app = flask.Flask(__name__)
app.config["DEBUG"] = True

def initDB():
    print("initializing DB ...")
    con = sqlite3.connect("/db/router.db")
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS routes (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_set, selector, selector_key, selector_value, destination, multipath, gateway)")
    con.commit()

def check_route(rule_set, destination):
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM routes WHERE rule_set='{rule_set}' AND destination='{destination}'")
    result = cur.fetchone()
    con.commit()
    return result

def create_route(rule_set, destination, selector=None, selector_key=None, selector_value=None, multipath=None, gateway=None):
    str_multipath = json.dumps({"multipath":multipath})
    str_selector_value = json.dumps({"selector_value":selector_value})
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute(f"INSERT INTO routes(rule_set, selector, selector_key, selector_value, destination, multipath, gateway) VALUES ('{rule_set}', '{selector}', '{selector_key}', '{str_selector_value}', '{destination}', '{str_multipath}', '{gateway}')")
    id = cur.lastrowid
    con.commit()
    return id

def update_route(id, rule_set, destination, selector=None, selector_key=None, selector_value=None, multipath=None, gateway=None):
    str_multipath = json.dumps({"multipath":multipath})
    str_selector_value = json.dumps({"selector_value":selector_value})
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute(f"UPDATE routes SET rule_set='{rule_set}', selector='{selector}', selector_key='{selector_key}', selector_value='{str_selector_value}', destination='{destination}', multipath='{str_multipath}', gateway='{gateway}' WHERE id={id}")
    con.commit()
    return id

def delete_route(rule_set, destination):
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute(f"DELETE FROM routes WHERE rule_set='{rule_set}' AND destination='{destination}'")
    con.commit()

def format_results(results):
    json_results={}
    result_arr=[]
    for result in results:
        row=[]
        for i in range(len(result)):
            if result[i] == "None":
                row.append(None)
            else:
                row.append(result[i])
        result_arr.append(
            {
                "id":row[0],
                "rule_set":row[1],
                "selector":row[2],
                "selector_key":row[3],
                "selector_value": json.loads(row[4])['selector_value'],
                "destination": row[5],
                "multipath":json.loads(row[6])['multipath'],
                "gateway":row[7]
            }
        )
    json_results['result'] = result_arr
    json_results['total'] = len(result_arr)
    return json_results

def get_all_routes():
    
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM routes")
    results = cur.fetchall()
    con.commit()
    return format_results(results=results)

def get_filtered_routes(selector_key,selector_value):
    routes = get_all_routes()['result']
    filtered_routes = []
    for route in routes:
        if route['selector'] == None:
            filtered_routes.append(route)
        else:
            if selector_key == route['selector_key']:
                    if selector_key == "nodePrefix":
                        in_list = False
                        for value in route['selector_value']:
                            if selector_value.startswith(value):
                                in_list = True
                        if (route['selector'] == "NotIn") and (not in_list):
                            filtered_routes.append(route)
                        if (route['selector'] == "In") and in_list:
                            filtered_routes.append(route)
                    
    return {"total":len(filtered_routes),"result":filtered_routes}

def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):

        token = None

        if 'Authorization' in request.headers:
            token = request.headers["Authorization"].strip()

        if not token:      
            return make_response(jsonify({'message': 'a valid token is missing'}),401)

        
        raw_token=os.environ.get("TOKEN")
        if isinstance(raw_token, (bytes, bytearray)):
            admin_token=str(raw_token,'utf-8').strip()
        else:
            admin_token=raw_token
            
        if admin_token == token:
            current_user = {"id":1, "name":"admin", "role":"admin"}
        else:
            return make_response(jsonify({'message': f'Forbidden'}),401)

        return f(current_user, *args, **kwargs)
    return decorator

@app.route('/api/v1/health', methods=['GET'])
def health():
    return jsonify({"status":"Ok"})


@app.route('/api/v1/route', methods=['POST'])
@token_required
def add(current_user):
    rule_set = request.json['rule_set']
    destination = request.json['destination']
    result = check_route(rule_set=rule_set,destination=destination)
    selector = None
    selector_key = None
    selector_value = None
    multipath = None
    gateway = None
    if "selector" in request.json:
        selector = request.json['selector']
    if "selector_key" in request.json:
        selector_key = request.json['selector_key']
    if "selector_value" in request.json: 
        selector_value = request.json['selector_value']
    if "multipath" in request.json:   
        multipath = request.json['multipath']
    if "gateway" in request.json: 
        gateway = request.json['gateway']

    if result:
        id = update_route(id=result[0],rule_set=rule_set,destination=destination,selector=selector,selector_key=selector_key,selector_value=selector_value,multipath=multipath,gateway=gateway)
        return {"message":f"updated with id:{id}"}
    else:
        id = create_route(rule_set=rule_set,destination=destination,selector=selector,selector_key=selector_key,selector_value=selector_value,multipath=multipath,gateway=gateway)
        return {"message":f"created with id:{id}"}

@app.route('/api/v1/route', methods=['GET'])
@token_required
def get_routes(current_user):
    filter=False
    if request.data:
        if ("selector_key" in request.json) and ("selector_value" in request.json):
            filter=True        
    if filter:
        return get_filtered_routes(selector_key=request.json["selector_key"],selector_value=request.json["selector_value"])
    return get_all_routes()

@app.route('/api/v1/route', methods=['DELETE'])
@token_required
def remove_route(current_user):
    delete=False
    if request.data:
        if ("rule_set" in request.json) and ("destination" in request.json):
            delete=True        
    if delete:
        delete_route(rule_set=request.json["rule_set"],destination=request.json["destination"])
        return {"message":"route deleted"}
    return {"message":"missing parameters"}
    

initDB()
app.run(host='0.0.0.0')