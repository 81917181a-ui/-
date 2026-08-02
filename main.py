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
    async def background_sync():
        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} commands.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    asyncio.create_task(background_sync())

# --- 運行設定を保持するセッションクラス ---
class TrainSession:
    def __init__(self, title: str, user_name: str, image_url: str = None):
        self.title = title
        self.user_name = user_name
        self.image_url = image_url
        self.railway = "未設定"
        self.event_link = "なし"
        self.section = "未設定"
        self.start_time = "06:00"
        self.end_time = "未設定"
        self.remarks = "なし"

    def make_embed(self):
        embed = discord.Embed(
            title=f"## 🚉 {self.title} のダイヤを作成中",
            color=discord.Color.blue()
        )
        embed.description = (
            f"現在の設定:\n"
            f"・運行先鉄道: {self.railway}\n"
            f"・イベントリンク: {self.event_link}\n"
            f"・走行区間: {self.section}\n"
            f"・開始時間: {self.start_time}\n"
            f"・終了時間: {self.end_time}\n"
            f"・備 考: {self.remarks}\n"
            f"───────────────────"
        )
        embed.add_field(name="主催者", value=self.user_name, inline=False)
        if self.image_url:
            embed.set_image(url=self.image_url)
        return embed

# --- 操作用UIパネル ---
class TrainControlView(ui.View):
    def __init__(self, session: TrainSession, target_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.session = session
        self.target_channel = target_channel

    @ui.button(label="⚙️ 設定を変更する", style=discord.ButtonStyle.primary, row=0)
    async def edit_settings(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TrainEditModal(self.session, self.target_channel))

    @ui.button(label="🚀 ダイヤ運行を確定・投稿", style=discord.ButtonStyle.success, row=0)
    async def publish_event(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(title="## ダイヤ運行予定", color=discord.Color.green())
        embed.add_field(name="主催者", value=self.session.user_name, inline=False)
        embed.add_field(name="運行先鉄道", value=self.session.railway, inline=False)
        embed.add_field(name="イベントリンク", value=self.session.event_link, inline=False)
        embed.add_field(name="走行区間", value=self.session.section, inline=False)
        embed.add_field(name="開始時刻", value=self.session.start_time, inline=True)
        embed.add_field(name="終了時刻", value=self.session.end_time, inline=True)
        if self.session.remarks != "なし":
            embed.add_field(name="備 考", value=self.session.remarks, inline=False)
        if self.session.image_url:
            embed.set_image(url=self.session.image_url)

        # 指定チャンネルにEmbedを送信し、操作パネルを終了状態に書き換える
        await self.target_channel.send(embed=embed)
        await interaction.response.edit_message(content=f"✅ {self.target_channel.mention} にダイヤ運行イベントを投稿しました！", embed=None, view=None)

# --- 設定変更モーダル ---
class TrainEditModal(ui.Modal, title="ダイヤ運行の各設定入力"):
    railway = ui.TextInput(label="運行先鉄道", placeholder="例: JR東日本", max_length=100)
    section = ui.TextInput(label="走行区間", placeholder="例: 東京 ～ 熱海", max_length=100)
    start_time = ui.TextInput(label="開始時間", placeholder="例: 06:00", max_length=50)
    end_time = ui.TextInput(label="終了時間", placeholder="例: 22:00", max_length=50)
    remarks = ui.TextInput(label="備 考", style=discord.TextStyle.paragraph, placeholder="注意事項など", required=False)

    def __init__(self, session: TrainSession, target_channel: discord.TextChannel):
        super().__init__()
        self.session = session
        self.target_channel = target_channel
        self.railway.default = self.session.railway if self.session.railway != "未設定" else ""
        self.section.default = self.session.section if self.session.section != "未設定" else ""
        self.start_time.default = self.session.start_time
        self.end_time.default = self.session.end_time if self.session.end_time != "未設定" else ""
        self.remarks.default = self.session.remarks if self.session.remarks != "なし" else ""

    async def on_submit(self, interaction: discord.Interaction):
        self.session.railway = self.railway.value
        self.session.section = self.section.value
        self.session.start_time = self.start_time.value
        self.session.end_time = self.end_time.value if self.end_time.value else "未設定"
        if self.remarks.value:
            self.session.remarks = self.remarks.value

        await interaction.response.edit_message(embed=self.session.make_embed(), view=TrainControlView(self.session, self.target_channel))

# --- コマンド群 ---

# 1. !manage event #チャンネル (またはチャンネルID)
@bot.group(name="manage", invoke_without_command=True)
async def manage(ctx):
    await ctx.send("使用方法: `!manage event #チャンネル名 (またはID)`")

@manage.command(name="event")
async def manage_event(ctx, channel: discord.TextChannel = None):
    if not channel:
        await ctx.send("❌ チャンネルを指定してください（例: `!manage event #general` または ID）")
        return

    image_url = ctx.message.attachments[0].url if ctx.message.attachments else None
    session = TrainSession(title="ダイヤ作成", user_name=ctx.author.mention, image_url=image_url)
    
    view = TrainControlView(session, channel)
    await ctx.send(f"📍 {channel.mention} 向けの運行作成パネルを起動します👇", embed=session.make_embed(), view=view)


# 2. !sendmessage #チャンネル (またはチャンネルID) [テキスト]
@bot.command(name="sendmessage")
async def send_message_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not channel or not message:
        await ctx.send("❌ 使い方: `!sendmessage #チャンネル名 (またはID) 送信したいメッセージ内容`")
        return
    
    try:
        await channel.send(message)
        await ctx.send(f"✅ {channel.mention} にメッセージを送信しました！")
    except Exception as e:
        await ctx.send(f"❌ 送信に失敗しました: {e}")


# 3. !serverchannelID (サーバー内全チャンネルのID取得)
@bot.command(name="serverchannelID")
async def server_channel_id(ctx):
    guild = ctx.guild
    if not guild:
        await ctx.send("❌ このコマンドはサーバー内で実行してください。")
        return

    text_channels = guild.text_channels
    if not text_channels:
        await ctx.send("❌ テキストチャンネルが見つかりませんでした。")
        return

    result_list = ["**📋 サーバー内テキストチャンネル一覧**"]
    for ch in text_channels:
        result_list.append(f"・{ch.name} : `{ch.id}`")

    # 文字数制限（2000文字）対策として結合して送信
    msg = "\n".join(result_list)
    if len(msg) > 2000:
        msg = msg[:1990] + "\n...(省略)"

    await ctx.send(msg)


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
