from os import getenv
# To create query parameters correctly
from urllib import parse

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient

from models.common import instance
from models.user import User

load_dotenv()

# Constants for authorization via Google
GOOGLE_CLIENT_ID = getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = getenv("GOOGLE_REDIRECT_URI")

TG_BOT_URL = getenv("TG_BOT_URL")
MONGO_URI = getenv("MONGO_URI")

client = AsyncIOMotorClient(MONGO_URI)
db = client.data
instance.set_db(db)

app = FastAPI(docs_url=None, redoc_url=None)


@app.get("/")
async def index():
	"""
	Why not?
	"""
	return {"text": "I don't think you're supposed to be here."}


@app.get("/tgbotlogin")
async def tgbotlogin():
	"""
	Redirect user to to Google's OAuth 2.0 server
	"""
	base_url = "https://accounts.google.com/o/oauth2/v2/auth?"
	scopes = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email"]
	params = {
		"client_id": GOOGLE_CLIENT_ID,
		"redirect_uri": GOOGLE_REDIRECT_URI,
		"response_type": "code",
		"scope": " ".join(scopes),
		"access_type": "offline"
	}
	return RedirectResponse(base_url + parse.urlencode(params))


@app.get("/auth")
async def auth(code: str):
	"""
	Handle the Google's OAuth 2.0 server response
	"""
	base_url = "https://oauth2.googleapis.com/token?"
	params = {
		"client_id": GOOGLE_CLIENT_ID,
		"client_secret": GOOGLE_CLIENT_SECRET,
		"code": code,
		"grant_type": "authorization_code",
		"redirect_uri": GOOGLE_REDIRECT_URI
	}
	# I know it looks terrible, but I don't know how to make it better, and asynchronously
	async with aiohttp.ClientSession() as session:
		async with session.post(base_url + parse.urlencode(params)) as response:
			data = await response.json()
			params = {
				"access_token": data["access_token"]
			}
			async with session.get("https://www.googleapis.com/oauth2/v2/userinfo?" + parse.urlencode(params)) as response:
				data = await response.json()
				user = User(
					given_name=data["given_name"],
					family_name=data["given_name"],
					email=data["email"],
					avatar_url=data["picture"]
				)
				await user.commit()
				base_url = TG_BOT_URL + "?"
				params = {
					"start": str(user.id),
				}
				url = base_url + parse.urlencode(params)
				print(url)
				return RedirectResponse(url)
