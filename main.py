import os
import asyncio
import discord
from discord import ui
from discord.ext import commands
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

# --- Discord Bot の設定 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

# --- 入力用モーダル ---
class EventModal(ui.Modal, title="ダイヤ運行イベント作成"):
    railway = ui.TextInput(label="運行先鉄道", placeholder="例: JR東日本", max_length=100)
    event_link = ui.TextInput(label="イベントリンク", placeholder="https://discord.gg/...", max_length=200, required=False)
    section = ui.TextInput(label="走行区間", placeholder="例: 東京 ～ 熱海", max_length=100)
    start_time = ui.TextInput(label="開始時刻", placeholder="例: 20:00", max_length=50)
    end_time = ui.TextInput(label="終了時刻", placeholder="例: 22:00", max_length=50)
    remarks = ui.TextInput(label="備 考", style=discord.TextStyle.paragraph, placeholder="注意事項など", required=False)

    def __init__(self, image_attachment: discord.Attachment = None):
        super().__init__()
        self.image_attachment = image_attachment

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="## ダイヤ運行予定",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="主催者", value=interaction.user.mention, inline=False)
        embed.add_field(name="運行先鉄道", value=self.railway.value, inline=False)
        
        if self.event_link.value:
            embed.add_field(name="イベントリンク", value=self.event_link.value, inline=False)
        else:
            embed.add_field(name="イベントリンク", value="（なし）", inline=False)
            
        embed.add_field(name="走行区間", value=self.section.value, inline=False)
        embed.add_field(name="開始時刻", value=self.start_time.value, inline=True)
        embed.add_field(name="終了時刻", value=self.end_time.value, inline=True)
        
        if self.remarks.value:
            embed.add_field(name="備 考", value=self.remarks.value, inline=False)

        if self.image_attachment:
            embed.set_image(url=self.image_attachment.url)

        await interaction.response.send_message(embed=embed)

# --- スラッシュコマンド ---
@bot.tree.command(name="manage", description="ダイヤ運行の管理を行います")
@discord.app_commands.describe(image="運行のサムネイルや路線図などの画像（任意）")
async def manage_event(interaction: discord.Interaction, image: discord.Attachment = None):
    modal = EventModal(image_attachment=image)
    await interaction.response.send_modal(modal)

# --- FastAPI のライフスパン設定 (非推奨警告の解消) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    token = os.getenv("BOT_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("Error: BOT_TOKEN is not set.")
    yield
    # 終了時の処理（必要に応じて）

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "Running", "service": "Train Schedule Bot"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
