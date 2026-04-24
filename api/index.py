import json
import requests
import random
from flask import Flask, jsonify, request, Response
from datetime import datetime, timedelta, timezone
# APK METHOD LAND BACKEND POSTED BY L1RSON110
class GameInfo:
    def __init__(self) -> None:
        self.TitleId:   str = "79AA2"
        self.SecretKey: str = "AAO9O4Q33MJ7OND344H6MQMQI9OWHHE1CF43EFIM1TX68K8FEY"
        self.AppCreds:  str = "OC|26885663497724255|8edbbed9478331eae09c5d44cb150f48"
        self.OculusAppId: str = "26885663497724255"
        self.EntitlementCheck: bool = True

    def GetAuthHeaders(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "X-SecretKey":  self.SecretKey
        }

    def GetTitle(self) -> str:
        return self.TitleId


settings = GameInfo()
app = Flask(__name__)
playfabCache = {}
muteCache = {}
valid_host = None

SuccessfulAuthy = ""
FailedAuthy = ""

def ReturnFunctionJson(data, funcname, funcparam={}):
    rjson = data.get("FunctionParameter", {})
    userId = rjson.get("CallerEntityProfile", {}).get("Lineage", {}).get("TitlePlayerAccountId")

    req = requests.post(
        url=f"https://{settings.TitleId}.playfabapi.com/Server/ExecuteCloudScript",
        json={
            "PlayFabId": userId,
            "FunctionName": funcname,
            "FunctionParameter": funcparam
        },
        headers=settings.GetAuthHeaders()
    )

    if req.status_code == 200:
        return jsonify(req.json().get("data").get("FunctionResult")), req.status_code
    else:
        return jsonify({}), req.status_code

def ValidateOculusAccount(Nonce: str, OculusId: str, ClientCustomId: str) -> tuple[bool, str | None, str | None, str | None]:
    VerifyNonceReq = requests.post(
        url="https://graph.oculus.com/user_nonce_validate",
        json={"access_token": settings.AppCreds, "nonce": Nonce, "user_id": OculusId},
        headers={"Content-Type": "application/json"}
    )
    print(json.dumps(VerifyNonceReq.json(), indent=2))
    if not VerifyNonceReq.json().get("is_valid"):
        return (False, None, None, "Nonce validation failed")

    OculusDataReq = requests.get(
        url=f"https://graph.oculus.com/{OculusId}?access_token={settings.AppCreds}&fields=org_scoped_id,alias",
        headers={"Content-Type": "application/json"}
    )
    print(json.dumps(OculusDataReq.json(), indent=2))
    if OculusDataReq.status_code != 200:
        return (False, None, None, "Failed to retrieve Oculus data")

    OculusData = OculusDataReq.json()
    OrgScope = OculusData.get("org_scoped_id")
    Alias = OculusData.get("alias")

    if not OrgScope:
        return (False, None, None, "Missing org_scoped_id")
    if not Alias:
        return (False, None, None, "Missing alias")

    ServerCustomId = f"OCULUS{OrgScope}"
    
    if ClientCustomId.startswith("OCULUS"):
        ClientOrgScope = ClientCustomId[6:]
    elif ClientCustomId.startswith("OC"):
        ClientOrgScope = ClientCustomId[2:]
    else:
        return (False, None, None, "Invalid CustomId prefix")
    
    if ClientOrgScope != OrgScope:
        return (False, None, None, "CustomId mismatch")

    return (True, ServerCustomId, Alias, None)

def CheckUserEntitlement(OculusId: str) -> tuple[bool, str | None, dict | None]:
    if not settings.EntitlementCheck:
        return (True, None, {"status": "skipped", "reason": "EntitlementCheck disabled"})
    
    EntitlementReq = requests.post(
        url=f"https://graph.oculus.com/{settings.OculusAppId}/verify_entitlement",
        data={
            "access_token": settings.AppCreds,
            "user_id": str(OculusId)
        }
    )
    
    print(f"Entitlement check response: {EntitlementReq.status_code}")
    print(json.dumps(EntitlementReq.json(), indent=2))
    
    result = EntitlementReq.json()
    response_info = {"status_code": EntitlementReq.status_code, "response": result}
    
    if EntitlementReq.status_code != 200:
        return (False, "Failed to verify entitlement", response_info)
    
    if "error" in result or not result.get("success", False):
        return (False, "User does not own this application", response_info)
    
    return (True, None, response_info)

@app.route("/", methods=["POST", "GET"])
def main():
    return "DISCORD.GG/APKMETHOD"

@app.route("https://canyonbouncers.vercel.app/api/PlayFabAuthentication", methods=["POST", "GET"])
def playfabauthentication():
    global valid_host
    
    request_host = request.headers.get("Host")
    
    if valid_host is None:
        valid_host = request_host
    
    if request_host != valid_host:
        return "", 404
    
    if "UnityPlayer" not in request.headers.get("User-Agent", ""):
        return Response(
            json.dumps({"BanMessage": "Unable To Validate User Agent Integrity.", "BanExpirationTime": "Indefinite"}, indent=1),
            mimetype="application/json"
        ), 403

    try:
        rjson = request.get_json()
        print(json.dumps(rjson, indent=2))
    except Exception as e:
        return jsonify({"Message": "Request body is missing or cannot be parsed.", "Error": "BadRequestBadBody"}), 400

    if rjson is None:
        return jsonify({"Message": "Request body is missing or cannot be parsed.", "Error": "BadRequestBadBody"}), 400

    AppVersion = rjson.get("AppVersion")
    OculusId = rjson.get("OculusId")
    Nonce = rjson.get("Nonce")
    CustomId = rjson.get("CustomId")
    Platform = rjson.get("Platform")
    AppId = rjson.get("AppId")

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    if CustomId is None:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Missing CustomId",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: Missing CustomId parameter```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate Account Ownership.", "Error": "FailedRequestNoCustomId"}), 403
    if Nonce is None:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Missing Nonce",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nFailure Reason: Missing Nonce parameter```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate Account Ownership.", "Error": "FailedRequestNoNonce"}), 403
    if AppId is None:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Missing AppId",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: Missing AppId parameter```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate AppId.", "Error": "FailedRequestNoAppId"}), 403
    if Platform is None:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Missing Platform",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: Missing Platform parameter```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Unable To Validate Platform", "Error": "Platform Validation Failed"}), 403
    if OculusId is None:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Missing OculusId",
                    "description": f"```IP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: Missing OculusId parameter```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate Account Ownership.", "Error": "FailedRequestNoOculusId"}), 403

    if AppId != settings.TitleId:
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Wrong AppId",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nAppId: {AppId}\nNonce: {Nonce}\nFailure Reason: Wrong AppId expected {settings.TitleId}```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate AppId.", "Error": "BadRequestAppIdMismatch"}), 403

    if Platform == "Windows":
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Invalid Platform",
                    "description": f"```OculusId: {OculusId}\nIP Address: {client_ip}\nPlatform: {Platform}\nNonce: {Nonce}\nFailure Reason: Platform must be Quest```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate Platform.", "Error": "ForbiddenPlatform"}), 403

    is_valid, server_custom_id, alias, error_reason = ValidateOculusAccount(
        Nonce=Nonce,
        OculusId=OculusId,
        ClientCustomId=CustomId
    )

    if not is_valid:
        print(f"Validation failed: {error_reason}")
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed Validation Error",
                    "description": f"```OculusId: {OculusId}\nCustomId: {CustomId}\nIP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: {error_reason}```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "Failed To Validate Account Ownership.", "Error": "ForbiddenValidationFailed"}), 403

    entitled, entitlement_error, entitlement_response = CheckUserEntitlement(OculusId)
    if not entitled:
        print(f"Entitlement check failed: {entitlement_error}")
        if FailedAuthy:
            fail_embed = {
                "content": None,
                "embeds": [{
                    "title": "Auth Failed No Game Entitlement",
                    "description": f"```OculusId: {OculusId}\nCustomId: {server_custom_id}\nAlias: {alias}\nIP Address: {client_ip}\nNonce: {Nonce}\nFailure Reason: {entitlement_error}\nEntitlement Response: {json.dumps(entitlement_response)}```",
                    "color": 0x8B0000
                }]
            }
            requests.post(url=FailedAuthy, json=fail_embed)
        return jsonify({"Message": "You do not own this application.", "Error": "ForbiddenNotEntitled"}), 403

    custom_id = server_custom_id
    print(f"Validated user with alias: {alias}")
    if custom_id == "OCULUS0":
        ban_req = requests.post(
            url=f"https://{settings.TitleId}.playfabapi.com/Admin/BanUsers",
            json={
                "Bans": [
                    {
                        "PlayFabId": rjson.get("currentPlayerId"),
                        "DurationInHours": None, 
                        "Reason": "CHEATING."
                    }
                ]
            },
            headers=settings.GetAuthHeaders()
        )
        if ban_req.status_code == 200:
            return jsonify({"Message": "bro was banned for: Lemonloader", "Error": "Banned"}), 403
        else:
            return jsonify({"Message": "Failed to ban user", "Error": "InternalError"}), 500

    url = f"https://{settings.TitleId}.playfabapi.com/Server/LoginWithServerCustomId"
    login_request = requests.post(
        url=url,
        json={
            "ServerCustomId": custom_id,
            "CreateAccount": True
        },
        headers=settings.GetAuthHeaders()
    )

    if login_request.status_code == 200:
        data = login_request.json().get("data")
        sessionTicket = data.get("SessionTicket")
        entityToken = data.get("EntityToken").get("EntityToken")
        playFabId = data.get("PlayFabId")
        entityType = data.get("EntityToken").get("Entity").get("Type")
        entityId = data.get("EntityToken").get("Entity").get("Id")

        print(requests.post(
            url=f"https://{settings.TitleId}.playfabapi.com/Server/LinkServerCustomId",
            json={
                "ForceLink": True,
                "ServerCustomId": custom_id,
                "PlayFabId": playFabId
            },
            headers=settings.GetAuthHeaders()
        ).json())

        AccountCreationIsoTimestamp_req = requests.post(
            url=f"https://{settings.TitleId}.playfabapi.com/Server/GetUserAccountInfo",
            json={"PlayFabId": playFabId},
            headers=settings.GetAuthHeaders()
        )
        AccountCreationIsoTimestamp = AccountCreationIsoTimestamp_req.json().get("data").get("UserInfo").get("Created")

        response_body = {
            "SessionTicket": sessionTicket,
            "EntityToken": entityToken,
            "PlayFabId": playFabId,
            "EntityId": entityId,
            "EntityType": entityType,
            "AccountCreationIsoTimestamp": AccountCreationIsoTimestamp
        }
        print(json.dumps(response_body, indent=2))

        if SuccessfulAuthy:
            success_embed = {
                "content": None,
                "embeds": [{
                    "title": "=== PlayFab Auth Success ===",
                    "description": f"```PlayFabId: {playFabId}\nOculusId: {OculusId}\nCustomId: {custom_id}\nAlias: {alias}\nIP Address: {client_ip}\nEntitlement Response: {json.dumps(entitlement_response)}```",
                    "color": 0x3498DB
                }]
            }
            requests.post(url=SuccessfulAuthy, json=success_embed)

        return jsonify(response_body), 200
    else:
        if login_request.status_code == 403:
            ban_info = login_request.json()
            if ban_info.get('errorCode') == 1002:
                ban_message = ban_info.get('errorMessage', "No ban message provided.")
                ban_details = ban_info.get('errorDetails', {})
                ban_expiration_key = next(iter(ban_details.keys()), None)
                ban_expiration_list = ban_details.get(ban_expiration_key, [])
                ban_expiration = ban_expiration_list[0] if len(ban_expiration_list) > 0 else "No expiration date provided."
                print(ban_info)
                return jsonify({
                    'BanMessage': ban_expiration_key,
                    'BanExpirationTime': ban_expiration
                }), 403
            else:
                error_message = ban_info.get('errorMessage', 'Forbidden without ban information.')
                return jsonify({
                    'Error': 'PlayFab Error',
                    'Message': error_message
                }), 403
        else:
            error_info = login_request.json()
            error_message = error_info.get('errorMessage', 'An error occurred.')
            return jsonify({
                'Error': 'PlayFab Error',
                'Message': error_message
            }), login_request.status_code

@app.route("https://canyonbouncers.vercel.app/api/CachePlayFabId", methods=["POST", "GET"])
def cacheplatfabid():
    rjson = request.get_json()

    playfabCache[rjson.get("PlayFabId")] = rjson

    return jsonify({"Message": "Success"}), 200

@app.route('https://canyonbouncers.vercel.app/api/TitleData', methods=['POST', 'GET'])
def titledata():
    if request.method != "POST":
        return "", 404
    response_data = {
        "AutoMuteCheckedHours": {
            "hours": 169
        },
        "AutoName_Adverbs": [
            "Cool", "Fine", "Bald", "Bold", "Half", 
            "Only", "Calm", "Fab", "Ice", "Mad", 
            "Rad", "Big", "New", "Old", "Shy"
        ],
        "AutoName_Nouns": [
            "Gorilla", "Chicken", "Darling", "Sloth", "King", 
            "Queen", "Royal", "Major", "Actor", "Agent", 
            "Elder", "Honey", "Nurse", "Doctor", "Rebel", 
            "Shape", "Ally", "Driver", "Deputy"
        ],
        "BundleBoardSign": "<color=#ff4141>DISCORD.GG/</color>",
        "BundleKioskButton": "<color=#ff4141>DISCORD.GG/</color>",
        "BundleKioskSign": "<color=#ff4141>DISCORD.GG/</color>",
        "BundleLargeSign": "<color=#ff4141>DISCORD.GG/</color>",
        "EmptyFlashbackText": "FLOOR TWO NOW OPEN\n FOR BUSINESS\n\nSTILL SEARCHING FOR\nBOX LABELED 2021",
        "EnableCustomAuthentication": True,
        "GorillanalyticsChance": 4320,
        "LatestPrivacyPolicyVersion": "2024.09.20",
        "LatestTOSVersion": "2024.09.20",
        "MOTD": "YOUR MOTD HERE",
        "SeasonalStoreBoardSign": "<color=#ff7241>FALL!</color>",
        "TOS_2024.09.20": "DISCORD.GG/",
        "TOBAlreadyOwnCompTxt": "DISCORD.GG/",
        "TOBAlreadyOwnPurchaseBundle": "BLABLABLA",
        "TOBDefCompTxt": "DISCORD.GG/",
        "TOBDefPurchaseBtnDefTxt": "BLABLABLA",
        "UseLegacyIAP": False
        
    }
    return jsonify(response_data)


@app.route("/api/GetAcceptedAgreements", methods=['POST', 'GET'])
def GetAcceptedAgreements():
    data = request.json

    return jsonify({"PrivacyPolicy": "1.1.67", "TOS": "11.05.22.2"}), 200

@app.route("/api/SubmitAcceptedAgreements", methods=['POST', 'GET'])
def SubmitAcceptedAgreements():
    data = request.json

    return jsonify({"PrivacyPolicy": "1.1.67", "TOS": "11.05.22.2"}), 200

@app.route('/api/GetName', methods=['POST', 'GET'])
def GetName():
    return jsonify({"result": f"GORILLA{random.randint(1000,9999)}"})

@app.route("/api/ConsumeOculusIAP", methods=["POST", "GET"])
def consumeoculusiap():
    rjson = request.get_json()

    accessToken = rjson.get("userToken")
    userId = rjson.get("userID")
    playFabId = rjson.get("playFabId")
    nonce = rjson.get("nonce")
    platform = rjson.get("platform")
    sku = rjson.get("sku")
    debugParams = rjson.get("debugParemeters")

    req = requests.post(
        url=f"https://graph.oculus.com/consume_entitlement?nonce={nonce}&user_id={userId}&sku={sku}&access_token={settings.AppCreds}",
        headers={
            "content-type": "application/json"
        }
    )

    if bool(req.json().get("success")):
        return jsonify({"result": True})
    else:
        return jsonify({"error": True})


@app.route("/api/TryDistributeCurrencyV2", methods=["POST"])
def TryDistributeCurrencyV2():
    if request.method != "POST":
        return "", 404

    rjson = request.json
    sr_a_day = 500  
    current_player_id = rjson.get("CallerEntityProfile", {}).get("Lineage", {}).get("MasterPlayerAccountId")

    get_data_response = requests.post(
        f"https://{settings.TitleId}.playfabapi.com/Server/GetUserReadOnlyData",
        headers=settings.GetAuthHeaders(),
        json={
            "PlayFabId": current_player_id,
            "Keys": ["DailyLogin"]
        }
    )

    daily_login_value = get_data_response.json().get("data").get("Data").get("DailyLogin", {}).get("Value", None)

    last_login_date = None
    if daily_login_value:
        last_login_date = datetime.fromisoformat(daily_login_value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    if not last_login_date or last_login_date < datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc):
        requests.post(
            f"https://{settings.TitleId}.playfabapi.com/Server/AddUserVirtualCurrency",
            headers=settings.GetAuthHeaders(),
            json={
                "PlayFabId": current_player_id,
                "VirtualCurrency": "SR",
                "Amount": sr_a_day
            }
        )

        requests.post(
            f"https://{settings.TitleId}.playfabapi.com/Server/UpdateUserReadOnlyData",
            headers=settings.GetAuthHeaders(),
            json={
                "PlayFabId": current_player_id,
                "Data": {
                    "DailyLogin": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat()
                }
            }
        )

    return "", 200

@app.route("/api/ShouldUserAutomutePlayer", methods=["POST", "GET"])
def shoulduserautomuteplayer():
    return jsonify(muteCache)

@app.route("/api/photon", methods=["POST", "GET"])
def photonauth():
    print(f"Received {request.method} request at /api/photon")
    AuthTicketUrl = f"https://{settings.TitleId}.playfabapi.com/Server/AuthenticateSessionTicket"
    VALID_APPS = [f"{settings.TitleId}"]

    if request.method == "GET":
        PlayerId = request.args.get("username")
        token = request.args.get("token")
        if not PlayerId or not token:
            return jsonify({"resultCode": 3, "message": "Failed to parse token from request", "userId": None, "nickname": None}), 400
        print(f"Player: {PlayerId} Has Authed In Old Update.")
        return jsonify({"resultCode": 1, "message": f"User: {PlayerId} Was Authed.", "username": PlayerId, "token": token}), 200

    elif request.method == "POST":
        newData = request.get_json()
        AppId = newData.get("AppId")
        AppVersion = newData.get("AppVersion")
        Ticket = newData.get("Ticket")
        Token = newData.get("Token")
        Nonce = newData.get("Nonce")
        Platform = newData.get("Platform")
        print(json.dumps(newData, indent=2))

        if AppId not in VALID_APPS:
            print(f"Invalid AppId: {AppId}")
            return jsonify({"ResultCode": 2, "Message": "Invalid AppId parameter", "Error": "BadRequestWrongAppId"}), 403

        if Platform != "Quest":
            print("Users Platform Is Not Quest")
            return jsonify({"Error": "Bad request", "ResultCode": 3, "Message": "Platform Must Be Quest Fella"}), 403

        AuthSessionTicketReq = requests.post(url=AuthTicketUrl, json={
            "SessionTicket": Ticket
        }, headers=settings.GetAuthHeaders())
        print(AuthSessionTicketReq)

        if AuthSessionTicketReq.status_code != 200:
            print(f"SessionTicket: {Ticket} Is Invalid")
            return jsonify({"ResultCode": 2, "Message": "Invalid SessionTicket parameter", "Error": "BadRequestBadSessionTicket"}), 403

        if AuthSessionTicketReq.status_code == 200:
            getdata = AuthSessionTicketReq.json().get("data").get("UserInfo", {})
            UserId = getdata.get("PlayFabId")
            
            AccountInfoReq = requests.post(
                url=f"https://{settings.TitleId}.playfabapi.com/Server/GetUserAccountInfo",
                json={"PlayFabId": UserId},
                headers=settings.GetAuthHeaders()
            )
            
            if AccountInfoReq.status_code != 200:
                print(f"Failed to get account info for UserId: {UserId}")
                return jsonify({"ResultCode": 3, "Message": "Failed to get account info", "Error": "BadRequestAccountInfo"}), 403
            
            accountData = AccountInfoReq.json().get("data", {}).get("UserInfo", {})
            print(f"AccountInfo response: {json.dumps(accountData, indent=2)}")
            ServerCustomIdInfo = accountData.get("ServerCustomIdInfo") or {}
            CustomId = ServerCustomIdInfo.get("CustomId") if ServerCustomIdInfo else None
            
            if not CustomId or not (CustomId.startswith("OCULUS") or CustomId.startswith("OC")):
                print(f"Invalid or missing ServerCustomId: {CustomId}")
                return jsonify({"ResultCode": 3, "Message": "Invalid ServerCustomId", "Error": "BadRequestInvalidCustomId"}), 403
            
            if CustomId.startswith("OCULUS"):
                OrgScopedCustomId = CustomId[6:]
            else:
                OrgScopedCustomId = CustomId[2:]
            print(f"OrgScopedCustomId: {OrgScopedCustomId}")

            OrgScopeUrl = f"https://graph.oculus.com/{OrgScopedCustomId}?access_token={settings.AppCreds}"
            GetOculusIdReq = requests.get(url=OrgScopeUrl, headers={"Content-Type": "application/json"})

            if "error" in GetOculusIdReq.json():
                print("User Did Not Pass The OrgScope Check.")
                return jsonify({"ResultCode": 3, "Message": "Did Not Pass OrgScopeId Checker", "Error": "BadRequestInvalidOrgScopeId"}), 403

            if UserId is None or len(UserId) != 16:
                print(f"UserId: {UserId} Is Not 16 Characters Long.")
                return jsonify({"ResultCode": 3, "Message": "Did Not UserId Length Checker", "Error": "BadRequestBadUserId"}), 403

            OculusId = GetOculusIdReq.json().get("id")
            print(f"Users OculusId Is: {OculusId}")

            VerifyNonceReq = requests.post(
                url="https://graph.oculus.com/user_nonce_validate",
                json={"access_token": settings.AppCreds, "nonce": newData.get("Nonce"), "user_id": OculusId},
                headers={"Content-Type": "application/json"}
            )
            print(VerifyNonceReq.json())
            nonce_json_data = VerifyNonceReq.json()

            if VerifyNonceReq.status_code != 200 or "is_valid" not in nonce_json_data:
                print(f"User: {UserId} Has Failed The Nonce Verification. Nonce: {Nonce}")
                return jsonify({"ResultCode": 1, "Message": "Failed Nonce Verification", "Error": "BadRequestInvalidNonce"}), 403

            print(f"{UserId} Was Authed Succesfully.")
            return jsonify({
                "ResultCode": 1,
                "Message": "Yay Servers Work Ig",
                "AppId": AppId,
                "AppVersion": AppVersion,
                "Nonce": Nonce,
                "OculusId": OculusId,
                "Ticket": Ticket,
                "Token": Token,
                "UserId": UserId
            }), 200

if __name__ == "__main__":
    app.run("0.0.0.0", 8080) # DISCORD.GG/APKMETHOD
