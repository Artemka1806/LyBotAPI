from os import getenv
# To create query parameters correctly
from urllib import parse
import re

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from pymongo.errors import DuplicateKeyError

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

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # Allow all origins
	allow_credentials=True,  # Allow cookies and authentication credentials
	allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
	allow_headers=["*"],  # Allow all headers
)


@app.head("/")
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
				user = None
				try:
					data = await response.json()
					await User.ensure_indexes()
					user = User(
						given_name=data["given_name"],
						family_name=data["family_name"],
						email=data["email"],
						avatar_url=data["picture"]
					)
					await user.commit()
				except (DuplicateKeyError, ValidationError):
					return {"text": "Користувач з такою поштою вже зареєстрований"}
				base_url = TG_BOT_URL + "?"
				params = {
					"start": str(user.id),
				}
				url = base_url + parse.urlencode(params)
				return RedirectResponse(url)


@app.get("/attendance")
async def get_attendance(timestamp: float = 0.0):
	data = []
	for doc in await User.find().to_list(length=None):
		d = doc.to_mongo()
		data.append(d)

	data = sorted(data, key=lambda x: x['family_name'])
	result = {}

	for entry in data:
		# Отримуємо групу та клас
		group = entry.get("group")
		if group is None:
			continue  # Пропускаємо, якщо немає групи

		# Визначаємо клас (перша частина групи) та підгрупу (група з буквою)
		class_num = group.split('-')[0]
		subgroup = group

		# Створюємо вкладені словники для класів та груп, якщо вони не існують
		if class_num not in result:
			result[class_num] = {}
		if subgroup not in result[class_num]:
			result[class_num][subgroup] = {}

		# Формуємо ім'я учня
		full_name = f"{entry['family_name']} {entry['given_name']}"

		# Створюємо об'єкт для кожного учня
		result[class_num][subgroup][full_name] = {
			"name": full_name,
			"avatar_url": entry.get("avatar_url", ""),
			"status": entry.get("status", 3),
			"message": entry.get("status_message", "")
		}

	# Функція для сортування підгруп за числовою та алфавітною частинами
	def sort_key(subgroup):
		match = re.match(r"(\d+)-([А-Яа-я])", subgroup)
		if match:
			return (int(match.group(1)), match.group(2))
		return (0, subgroup)

	# Сортування класів та підгруп
	sorted_result = {class_num: dict(sorted(result[class_num].items(), key=lambda x: sort_key(x[0])))
		for class_num in sorted(result.keys(), key=int)}
	return sorted_result
