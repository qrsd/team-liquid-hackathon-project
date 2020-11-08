# bot.py
import os
import discord
import datetime
import time
import re
import itertools
import mysql.connector

from asyncio import sleep
from dotenv import load_dotenv
from discord.ext import tasks, commands
from discord.ext.commands import ConversionError
from discord import Game
from discord.utils import get

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER = os.getenv('SERVER')
USER = os.getenv('USER')
PASS = os.getenv('PASS')
DB = os.getenv('DB')

# mySQL
try:
    mydb = mysql.connector.connect(
    host=SERVER,
    user=USER,
    password=PASS,
    database=DB
    )
except Exception as e:
    print(e)
    
cursor = mydb.cursor(dictionary=True)

# add query
def addToTable(query):
    add_info = ('INSERT INTO lfs_table'
                  '(ServerName,ChannelName,UserTag,UserID,Location,MatchDate,GameRank,OptionalInfo)'
                  'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)')
    data_info = (query[0], query[1], query[2], query[3], query[4], query[5], query[6], query[7])
    cursor.execute(add_info, data_info)
    mydb.commit()

# check for old matches every hour
# remove
@tasks.loop(hours=1)
async def removeFromTable():
    await afterLoop()

@removeFromTable.after_loop
async def afterLoop():
    get_table = ('SELECT * FROM lfs_table')
    remove_command = ('DELETE FROM lfs_table WHERE ID=')
    cursor.execute(get_table)
    cursorInfo = cursor.fetchall()
    mydb.rollback()
    for row in cursorInfo:
        if row['MatchDate']\
            < (datetime.datetime.now() + datetime.timedelta(hours = 1)):
                remove_command_id = remove_command + str(row['ID'])
                cursor.execute(remove_command_id)
                remove_command_id = None
                mydb.commit()

# check matches
async def checkMatches():
    get_table = ('SELECT a.* '
                'FROM lfs_table a '
                'JOIN (SELECT ServerName, ChannelName, COUNT(*) '
                'FROM lfs_table '
                'GROUP BY ServerName, ChannelName '
                'HAVING count(*) > 1) b '
                'ON a.ServerName = b.ServerName '
                'AND a.ChannelName = b.ChannelName '
                'ORDER BY a.ServerName')
    cursor.execute(get_table)

    for x,y in itertools.combinations(cursor,2):
      if x['Location'] == y['Location'] \
        and checkRank(x['GameRank'], y['GameRank'])\
            and checkTime(x['MatchDate'],y['MatchDate']):
                await matchFound(x,y)

def checkRank(x,y):
    x2=y2=None
    if x > 10:
      x = x // 10
      x2 = x % 10
    if y > 10:
      y = y // 10
      y2 = y % 10
    if x <= y:
          return True
    else:
        return False

def checkTime(x,y):
    if x.date() != y.date():
        return False
    elif (x + datetime.timedelta(hours = 1)).time() >= y.time()\
      and (x + datetime.timedelta(hours = -1)).time() <= y.time():
        return True
    else:
        return False

# Bot commands
bot = commands.Bot(command_prefix='-', case_insensitive=True) 

#-lfs 
@bot.command() 
async def LFS(ctx, *, arg):
    try:
        myList = arg.split(" ")
        validator(myList)
        author = ctx.author.name + '#' + ctx.author.discriminator
        authorID = ctx.author.id
        query = parseList(ctx.guild.name, ctx.channel.name, author, authorID, myList)
        addToTable(query)
        await checkMatches()
    except Exception as e:
        print(e)
        await validationError(ctx)
    
# parsing
def parseList(server,channel,userTag, userID, arg):
    SERVER_NAME = CHANNEL_NAME = LOCATION = DATETIME = RANK = OPTIONAL = None
    
    # Discord info
    SERVER_NAME = server
    CHANNEL_NAME = channel
    USERTAG = userTag
    USERID = userID

    # Location
    if arg[0].lower() == 'naw' or arg[0].lower() == 'west':
        LOCATION = 0
    else:
        LOCATION = 1
    
    # Date
    now = datetime.datetime.now()
    if arg[1].lower() == 'today' or arg[1].lower() == 'tonight':
        DATETIME = now.date()
    elif arg[1].lower() == 'tomorrow':
        DATETIME = now.date() + datetime.timedelta(days = 1)
    else:
        DATETIME = str(now.year) + '-' + str(arg[1])

    DATETIME = str(DATETIME)

    # Time
    timeArg = arg[2]
    if not ':' in timeArg: 
        timeArg = timeArg[: len(timeArg) - 2] + ':00' + timeArg[len(timeArg) - 2 :]
    timeStruct = datetime.datetime.strptime(timeArg, '%I:%M%p')
    if arg[3].lower() == 'est':
        timeStruct = timeStruct + datetime.timedelta(hours = -3)
    if arg[3].lower() == 'cst':
        timeStruct = timeStruct + datetime.timedelta(hours = -2)
    strTime = datetime.datetime.strftime(timeStruct,'%H:%M:%S')
    DATETIME = DATETIME + ' ' + strTime
    DATETIME = datetime.datetime.strptime(DATETIME, '%Y-%m-%d %H:%M:%S')
        
    # Rank
    ranks = ['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'immortal', 'radiant']
    rankArg = arg[4]
    rankVal = None
    rankPlus = False
    if '+' in rankArg:
        rankArg = rankArg.replace('+','')
        rankPlus = True
    if '-' in rankArg:
        rankList = rankArg.split('-')
        rankVal = ([index for index, rank in enumerate(ranks) if rankList[0] in rank][0] + 1)*10 \
            + ([index for index, rank in enumerate(ranks) if rankList[1] in rank][0] + 1)
    else:   
        rankVal = [index for index, rank in enumerate(ranks) if rankArg in rank][0] + 1
        if rankPlus:
            rankVal = (rankVal * 10 + 8) % 80
    RANK = rankVal

    # Optional
    OPTIONAL = ' '.join(map(str,arg[5:]))

    dbList=[SERVER_NAME, CHANNEL_NAME, USERTAG, USERID, LOCATION, DATETIME, RANK, OPTIONAL]

    return dbList

# lfs error 
@LFS.error
async def info_error(ctx, error):
    await validationError(ctx)

# Alive
@bot.event 
async def on_ready():
    print('Logged in as:')
    print(bot.user.name)
    await bot.change_presence(activity=discord.Activity(name='-lfs', type=5))

# Validators
def validator(arg):
    # location
    location = ['NAW','NAE', 'west','east']
    if not any(arg[0].lower() in loc.lower() for loc in location):
        raise Exception('Invalid Location')

    # date
    days = ['today', 'tonight' , 'tomorrow']
    if any(arg[1].lower() in day.lower() for day in days) or validDate(arg[1]):
        pass
    else:
        raise Exception('Invalid Date')

    # time
    if not validTime(arg[2]):
        raise Exception('Invalid Time')
    
    # timezones
    timezones = ['pst','cst','est']
    if not any(arg[3].lower() in timezone.lower() for timezone in timezones):
        raise Exception('Invalid Timezone')

    # ranks
    if not validRank(arg[4]):
        raise Exception('Invalid rank')
    
def validDate(arg):
    try:
        datetime.datetime.strptime(arg, '%m-%d')
        return True
    except ValueError:
        return False

def validTime(arg):
    if not ':' in arg: 
        arg = arg[: len(arg) - 2] + ':00' + arg[len(arg) - 2 :]
    try:
        time.strptime(arg, '%I:%M%p')
        return True
    except ValueError:
         return False

def validRank(arg):
    ranks = ['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'immortal', 'radiant']
    
    if '+' in arg:
        arg = arg.replace('+','')

    if '-' in arg:
        rankList = arg.split('-')
        if any(rankList[0].lower() in rank.lower() for rank in ranks) \
            and any(rankList[1].lower() in rank.lower() for rank in ranks) \
                and [index for index, rank in enumerate(ranks) if rankList[0] in rank][0] < [index for index, rank in enumerate(ranks) if rankList[1] in rank][0]:
            return True
    elif any(arg.lower() in rank.lower() for rank in ranks):
        return True
    else:
        return False

async def validationError(ctx):
    title = '**Invalid Format**'
    emb = discord.Embed(title=title, color=0xFF0000)
    emb.add_field(name='\u200b*Valid Format*', value = '```-LFS [Location] [Date] [Time] [Rank] [Optional]```\u200b')
    emb.add_field(name='*Example*', value = '```-LFS NAW today 11PM PST radiant bo3```\u200b',inline = False)
    emb.add_field(name='*Valid Locations*',value = '```NAW/West\nNAE/East```',inline=True)
    emb.add_field(name='*Valid Dates*',value = '```\nToday\nTomorrow\n(MM/DD)\n11-6```',inline=True)
    emb.add_field(name='*Valid Time*',value = '```(time timezone)\n11PM PST\n11:30PM PST```\u200b',inline=True)
    emb.add_field(name='*Valid Ranks*',value = '```Iron\nBronze\nSilver\nGold\nPlatinum\nDiamond\nImmortal\nRadiant```',inline=True)
     
    await ctx.author.send(embed=emb)

async def matchFound(x,y):
    title = '**Match Found!**'
    #location
    if x['Location'] == 1:
        location = 'East'
    else:
        location = 'West'
    #Date/Time
    whenTime = datetime.datetime.strftime(x['MatchDate'],'%m-%d %I:%M%p')
    #Rank
    ranksInfo = ['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'immortal', 'radiant']
    x2 = y2 = None
    if x['GameRank'] > 10:
        x2 = x['GameRank']//10
        y2 = x['GameRank']%10
        rank = ranksInfo[x2-1]+ '-' + ranksInfo[y2-1]
    else:
        rank = ranksInfo[x['GameRank']-1]
    
    #User Info
    matchedUser1 = x['UserID'] 
    matchedUser2 = y['UserID']

    #Send user 1
    matchInfo = location + ' ' + whenTime + ' ' + rank + ' ' + y['OptionalInfo']
    advertisment = '#TLWIN #TLWIN #TLWIN #TLWIN' 
    outro = '```' + advertisment + '```'
    user = '```' + y['UserTag'] + '```\u200b'
    scrimInfo = '```' + matchInfo + '```\u200b'
    emb = discord.Embed(title=title, color=0x00ff00)
    emb.set_thumbnail(url='https://i.ibb.co/8jrY3q1/hiclipart-com.png')
    emb.add_field(name='\u200b*Scrim Information*', value = scrimInfo, inline = False)
    emb.add_field(name='*User*', value = user,inline = False)
    emb.add_field(name='*Good Luck! Have fun!*',value = outro,inline=False)
    usr1 = await bot.fetch_user(int(matchedUser1))
    await usr1.send(embed=emb)

    #Send user 2
    matchInfo = location + ' ' + whenTime + ' ' + rank + ' ' + x['OptionalInfo']
    advertisment = '#TLWIN #TLWIN #TLWIN #TLWIN' 
    outro = '```' + advertisment + '```'
    user = '```' + x['UserTag'] + '```\u200b'
    scrimInfo = '```' + matchInfo + '```\u200b'
    emb = discord.Embed(title=title, color=0x00ff00)
    emb.set_thumbnail(url='https://i.ibb.co/8jrY3q1/hiclipart-com.png')
    emb.add_field(name='\u200b*Scrim Information*', value = scrimInfo, inline = False)
    emb.add_field(name='*User*', value = user,inline = False)
    emb.add_field(name='*Good Luck! Have fun!*',value = outro,inline=False)
    usr2 = await bot.fetch_user(int(matchedUser2))
    await usr2.send(embed=emb)

removeFromTable.start()
bot.run(TOKEN)