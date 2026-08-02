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
    def __init__(self, title: str, user_name: str, event_link: str = "なし", image_url: str = None):
        self.title = title
        self.user_name = user_name
        self.event_link = event_link
        self.image_url = image_url
        self.railway = "未設定"
        self.section = "未設定"
        self.start_time = "23:00"
        self.end_time = "0:00"
        self.remarks = "未設定"

    def make_embed(self):
        embed = discord.Embed(
            title=f"🚉 {self.title} のダイヤを作成中",
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

# --- 操作用UIパネル（スレッド内用） ---
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
        embed = discord.Embed(title="ダイヤ運行予定", color=discord.Color.green())
        embed.add_field(name="主催者", value=self.session.user_name, inline=False)
        embed.add_field(name="運行先鉄道", value=self.session.railway, inline=False)
        embed.add_field(name="イベントリンク", value=self.session.event_link, inline=False)
        embed.add_field(name="走行区間", value=self.session.section, inline=False)
        embed.add_field(name="開始時刻", value=self.session.start_time, inline=True)
        embed.add_field(name="終了時刻", value=self.session.end_time, inline=True)
        if self.session.remarks != "未設定":
            embed.add_field(name="備 考", value=self.session.remarks, inline=False)
        if self.session.image_url:
            embed.set_image(url=self.session.image_url)

        # ターゲットチャンネルに最終結果を送信
        await self.target_channel.send(embed=embed)
        await interaction.response.edit_message(content="✅ ダイヤ運行イベントが正式に確定・投稿されました！このスレッドはまもなく閉じられます。", embed=None, view=None)
        
        # スレッドをアーカイブ（終了）する
        try:
            if isinstance(interaction.channel, discord.Thread):
                await asyncio.sleep(3)
                await interaction.channel.edit(archived=True, locked=True)
        except Exception:
            pass

# --- 設定変更モーダル ---
class TrainEditModal(ui.Modal, title="ダイヤ運行の各設定入力"):
    railway = ui.TextInput(label="運行先鉄道", placeholder="例: 尾羽旧電鉄", max_length=100)
    event_link = ui.TextInput(label="イベントリンク", placeholder="https://discord.gg/... または なし", max_length=200, required=False)
    section = ui.TextInput(label="走行区間", placeholder="例: 尾羽急本線", max_length=100)
    start_time = ui.TextInput(label="開始時間", placeholder="例: 23:00", max_length=50)
    end_time = ui.TextInput(label="終了時間", placeholder="例: 0:00", max_length=50)
    remarks = ui.TextInput(label="備 考", style=discord.TextStyle.paragraph, placeholder="例: 終電運行", required=False)

    def __init__(self, session: TrainSession, target_channel: discord.TextChannel):
        super().__init__()
        self.session = session
        self.target_channel = target_channel
        self.railway.default = self.session.railway if self.session.railway != "未設定" else ""
        self.event_link.default = self.session.event_link if self.session.event_link != "なし" else ""
        self.section.default = self.session.section if self.session.section != "未設定" else ""
        self.start_time.default = self.session.start_time
        self.end_time.default = self.session.end_time
        self.remarks.default = self.session.remarks if self.session.remarks != "未設定" else ""

    async def on_submit(self, interaction: discord.Interaction):
        self.session.railway = self.railway.value
        self.session.event_link = self.event_link.value if self.event_link.value else "なし"
        self.session.section = self.section.value
        self.session.start_time = self.start_time.value
        self.session.end_time = self.end_time.value
        if self.remarks.value:
            self.session.remarks = self.remarks.value

        await interaction.response.edit_message(embed=self.session.make_embed(), view=TrainControlView(self.session, self.target_channel))

# --- コマンド群 ---

@bot.group(name="manage", invoke_without_command=True)
async def manage(ctx):
    await ctx.send("使用方法: `!manage event #チャンネル名 (またはID) [イベントリンク(任意)]`")

@manage.command(name="event")
async def manage_event(ctx, channel: discord.TextChannel = None, event_link: str = "なし"):
    if not channel:
        await ctx.send("❌ チャンネルを指定してください（例: `!manage event #general https://discord.gg/...`）")
        return

    # 実行時に添付された画像があれば取得
    image_url = ctx.message.attachments[0].url if ctx.message.attachments else None
    session = TrainSession(title="ダイヤ作成", user_name=ctx.author.mention, event_link=event_link, image_url=image_url)
    
    # 1. 宛先チャンネルにベースとなるメッセージを送信
    base_msg = await channel.send(f"🚉 **{ctx.author.display_name}** さんがダイヤ運行の作成を開始しました（スレッドをご確認ください👇）")
    
    # 2. そのメッセージを親としてパブリックスレッドを作成
    thread = await channel.create_thread(
        name=f"ダイヤ作成-{ctx.author.display_name}",
        message=base_msg,
        type=discord.ChannelType.public_thread
    )

    # 3. スレッドの中に操作パネルを送信
    view = TrainControlView(session, channel)
    await thread.send(embed=session.make_embed(), view=view)
    
    # 実行元のチャットに案内を返す
    await ctx.send(f"✅ {thread.mention} を作成しました！スレッドに移動して設定を行ってください。", delete_after=10)

@bot.command(name="sendmessage")
async def send_message_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not channel or not message:
        await ctx.send("❌ 使い方: `!sendmessage #チャンネル名 (またはID) 送信したいメッセージ内容` （画像を添付して実行可能）")
        return
    
    try:
        files = [await att.to_file() for att in ctx.message.attachments] if ctx.message.attachments else []
        await channel.send(message, files=files)
        await ctx.send(f"✅ {channel.mention} にメッセージを送信しました！")
    except Exception as e:
        await ctx.send(f"❌ 送信に失敗しました: {e}")

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
