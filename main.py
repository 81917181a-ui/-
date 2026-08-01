import os
import asyncio
import discord
from discord import ui
from discord.ext import commands
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

# --- Discord Bot の設定 (プレフィックスを '!' に設定) ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# --- 入力用モーダル ---
class EventModal(ui.Modal, title="ダイヤ運行イベント作成"):
    railway = ui.TextInput(label="運行先鉄道", placeholder="例: JR東日本", max_length=100)
    event_link = ui.TextInput(label="イベントリンク", placeholder="https://discord.gg/...", max_length=200, required=False)
    section = ui.TextInput(label="走行区間", placeholder="例: 東京 ～ 熱海", max_length=100)
    start_time = ui.TextInput(label="開始時刻", placeholder="例: 20:00", max_length=50)
    end_time = ui.TextInput(label="終了時刻", placeholder="例: 22:00", max_length=50)
    remarks = ui.TextInput(label="備 考", style=discord.TextStyle.paragraph, placeholder="注意事項など", required=False)

    def __init__(self, target_channel: discord.TextChannel, image_url: str = None):
        super().__init__()
        self.target_channel = target_channel
        self.image_url = image_url

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

        if self.image_url:
            embed.set_image(url=self.image_url)

        # 指定されたチャンネルにEmbedを送信
        await self.target_channel.send(embed=embed)
        await interaction.response.send_message(f"✅ {self.target_channel.mention} にダイヤ運行予定を投稿しました！", ephemeral=True)

# --- 通常コマンド: !manage event [#チャンネル名] ---
@bot.group(name="manage", invoke_without_command=True)
async def manage(ctx):
    await ctx.send("使用方法: `!manage event #チャンネル名` （画像を添付して実行することも可能です）")

@manage.command(name="event")
async def manage_event(ctx, channel: discord.TextChannel = None):
    # チャンネルが指定されていない場合はコマンドを実行したチャンネルを対象にする
    target_channel = channel if channel else ctx.channel
    
    # メッセージに画像が添付されているか確認
    image_url = None
    if ctx.message.attachments:
        image_url = ctx.message.attachments[0].url

    # モーダルをポップアップ表示
    modal = EventModal(target_channel=target_channel, image_url=image_url)
    
    # discord.pyの仕様上、メッセージコマンドからモーダルを出すためには、
    # 独自のViewに紐付けるか、Interactionを経由する必要があります。
    # ここではボタンを押してモーダルを開くViewを送信します。
    class ModalView(ui.View):
        @ui.button(label="ダイヤ運行フォームを開く", style=discord.ButtonStyle.primary)
        async def open_modal(self, button_interaction: discord.Interaction, button: ui.Button):
            await button_interaction.response.send_modal(modal)

    await ctx.send("下のボタンを押して運行詳細を入力してください👇", view=ModalView(), delete_after=60)

# --- FastAPI のライフスパン設定 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("BOT_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("Error: BOT_TOKEN is not set.")
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "Running", "service": "Train Schedule Bot"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
