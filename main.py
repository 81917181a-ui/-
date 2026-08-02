import os
import asyncio
import discord
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
    def __init__(self, title: str, user_mention: str, event_link: str = "なし", image_url: str = None):
        self.title = title
        self.user_mention = user_mention
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
        embed.add_field(name="主催者", value=self.user_mention, inline=False)
        if self.image_url:
            embed.set_image(url=self.image_url)
        return embed

# --- コマンド群 ---

@bot.group(name="manage", invoke_without_command=True)
async def manage(ctx):
    await ctx.send("使用方法: `!manage event #チャンネル名 [イベントリンク(任意)]`")

@manage.command(name="event")
async def manage_event(ctx, channel: discord.TextChannel = None, event_link: str = "なし"):
    if not channel:
        await ctx.send("❌ チャンネルを指定してください（例: `!manage event #general https://discord.gg/...`）")
        return

    try:
        await ctx.message.delete()
    except Exception:
        pass

    image_url = ctx.message.attachments[0].url if ctx.message.attachments else None
    session = TrainSession(title="ダイヤ作成", user_mention=ctx.author.mention, event_link=event_link, image_url=image_url)
    
    panel_msg = await channel.send(embed=session.make_embed())
    
    thread = await channel.create_thread(
        name=f"ダイヤ作成-{ctx.author.display_name}",
        message=panel_msg,
        type=discord.ChannelType.public_thread
    )

    questions = [
        ("運行先鉄道", "運行先の鉄道名を入力してください（例: 尾羽旧電鉄）"),
        ("走行区間", "走行区間を入力してください（例: 尾羽急本線）"),
        ("開始時間", "開始時間を入力してください（例: 23:00）"),
        ("終了時間", "終了時間を入力してください（例: 0:00）"),
        ("備 考", "備考を入力してください（例: 終電運行 / なしなら 「なし」等）")
    ]

    def check(m):
        return m.author == ctx.author and m.channel == thread

    try:
        for attr, q_text in questions:
            q_msg = await thread.send(f"{ctx.author.mention} {q_text}")
            msg = await bot.wait_for('message', timeout=1800.0, check=check)
            
            try:
                await msg.delete()
                await q_msg.delete()
            except Exception:
                pass

            if attr == "運行先鉄道":
                session.railway = msg.content
            elif attr == "走行区間":
                session.section = msg.content
            elif attr == "開始時間":
                session.start_time = msg.content
            elif attr == "終了時間":
                session.end_time = msg.content
            elif attr == "備 考":
                session.remarks = msg.content

            await panel_msg.edit(embed=session.make_embed())

        final_embed = discord.Embed(title="ダイヤ運行予定", color=discord.Color.green())
        final_embed.add_field(name="主催者", value=session.user_mention, inline=False)
        final_embed.add_field(name="運行先鉄道", value=session.railway, inline=False)
        final_embed.add_field(name="イベントリンク", value=session.event_link, inline=False)
        final_embed.add_field(name="走行区間", value=session.section, inline=False)
        final_embed.add_field(name="開始時刻", value=session.start_time, inline=True)
        final_embed.add_field(name="終了時刻", value=session.end_time, inline=True)
        if session.remarks != "未設定" and session.remarks != "なし":
            final_embed.add_field(name="備 考", value=session.remarks, inline=False)
        if session.image_url:
            final_embed.set_image(url=session.image_url)

        await panel_msg.edit(content=f"✅ ダイヤ運行予定が正式に投稿されました！ (メッセージID: `{panel_msg.id}`)", embed=final_embed)
        await thread.send("✅ すべての設定が完了しました！このスレッドを閉じます。")
        await asyncio.sleep(3)
        await thread.edit(archived=True, locked=True)

    except asyncio.TimeoutError:
        await thread.send("⏰ 30分間応答がなかったため、ダイヤ作成をキャンセルしました。")
        await asyncio.sleep(3)
        try:
            await panel_msg.delete()
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass

# --- イベントキャンセル機能 ---
@bot.group(name="event", invoke_without_command=True)
async def event_group(ctx):
    await ctx.send("使用方法: `!event cancel [キャンセル理由] [messageID]`")

@event_group.command(name="cancel")
async def event_cancel(ctx, reason: str = None, message_id: int = None):
    if not reason or not message_id:
        await ctx.send("❌ 使い方: `!event cancel [キャンセル理由] [messageID]`")
        return

    try:
        await ctx.message.delete()
    except Exception:
        pass

    # 実行されたチャンネル、またはサーバー内から該当のメッセージを探す
    target_message = None
    for channel in ctx.guild.text_channels:
        try:
            target_message = await channel.fetch_message(message_id)
            break
        except discord.NotFound:
            continue
        except discord.Forbidden:
            continue

    if not target_message:
        await ctx.send("❌ 指定されたIDのメッセージが見つかりませんでした。", delete_after=10)
        return

    try:
        if target_message.embeds:
            embed = target_message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "🚫 【ダイヤ運行中止】"
            embed.add_field(name="キャンセル理由", value=reason, inline=False)
            await target_message.edit(content="⚠️ **このダイヤ運行は中止されました。**", embed=embed)
            await ctx.send(f"✅ メッセージID `{message_id}` のイベントをキャンセル（中止）に変更しました。", delete_after=10)
        else:
            await ctx.send("❌ 指定されたメッセージにはEmbedが含まれていません。", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ キャンセル処理に失敗しました: {e}", delete_after=10)

@bot.command(name="sendmessage")
async def send_message_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not channel or not message:
        await ctx.send("❌ 使い方: `!sendmessage #チャンネル名 (またはID) 送信したいメッセージ内容`")
        return
    
    try:
        await ctx.message.delete()
    except Exception:
        pass

    try:
        files = [await att.to_file() for att in ctx.message.attachments] if ctx.message.attachments else []
        await channel.send(message, files=files)
    except Exception as e:
        await ctx.send(f"❌ 送信に失敗しました: {e}")

@bot.command(name="serverchannelID")
async def server_channel_id(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    guild = ctx.guild
    if not guild:
        await ctx.send("❌ このサーバー内で実行してください。")
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
