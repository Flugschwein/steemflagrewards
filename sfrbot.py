import asyncio
import datetime
import logging
import sqlite3
import os
import discord

from beem import Steem
from beem.account import Account
from beem.comment import Comment
from beem.exceptions import AccountDoesNotExistsException, ContentDoesNotExistsException, VotingInvalidOnArchivedPost
from beem.instance import set_shared_steem_instance
from beem.nodelist import NodeList
from beem.utils import construct_authorperm, addTzInfo
import config
from discord.ext.commands import Bot

logging.basicConfig(level=logging.INFO,
                    filename=datetime.datetime.utcnow().strftime('logs/steemflagrewards-%Y-%d-%m-%H-%M.txt'))

db = sqlite3.connect('SFR.db')
cursor = db.cursor()

nodes = NodeList().get_nodes()
stm = Steem(node=nodes)
set_shared_steem_instance(stm)


##################################################
# Uncomment for the initial setup of the database
# cursor.execute('''CREATE TABLE steemflagrewards
# (flagger TEXT, comment TEXT, post TEXT, category TEXT, created TEXT, included BOOL, payout REAL, queue BOOL, weight REAL, followon BOOL)''')
# cursor.execute('CREATE TABLE flaggers (name TEXT)')
# cursor.execute('CREATE TABLE sdl (name TEXT, created TEXT, delegation BOOL)')
# db.commit()
##################################################


def check_cat(comment):
    """Returning the matching category of abuse"""
    cats = []
    for cat in sorted(config.CAT_DESCRIPTION.keys()):
        if cat in comment.lower():
            if cat == 'spam' and 'comment spam' in comment.lower():
                continue
            cats.append(cat)
    return cats


def get_wait_time(account):
    """Get the time (in seconds) required until the next comment can be posted.
    Only works for one 'queued' comment.
    """
    account.refresh()
    last_post_timedelta = addTzInfo(datetime.datetime.utcnow()) - account['last_post']
    return max(0, config.STEEM_MIN_REPLY_INTERVAL - last_post_timedelta.total_seconds())


def report():
    """Posting a report post with the flaggers set as beneficiaries."""
    cursor.execute('DELETE FROM flaggers;')
    cursor.execute(
        'INSERT INTO flaggers SELECT DISTINCT flagger FROM steemflagrewards WHERE included == 0 ORDER BY created ASC LIMIT 8;')
    sql = cursor.execute(
        'SELECT \'[Comment](https://steemit.com/\' || post || \'#\' || comment || \')\', \'@\' || flagger, \'$\' || ROUND(payout, 3), category'
        'FROM steemflagrewards WHERE included == 0 AND flagger IN flaggers;')
    db.commit()
    table = '|Link|Flagger|Removed Rewards|Category|\n|:----|:-------|:---------------:|:--------|'
    for q in sql.fetchall():
        table += '\n|{}|{}|{}|{}|'.format(q[0], q[1], q[2], q[3])
    body = '## This post triggers once we have approved flags from 8 distinct flaggers via the SteemFlagRewards Abuse ' \
           'Fighting Community on our [Discord](https://discord.gg/7pqKmg5) ' \
           '\n\nhttps://steemitimages.com/DQmTJj2SXdXcYLh3gtsziSEUXH6WP43UG6Ltoq9EZyWjQeb/frpaccount.jpg\n\nFlaggers ' \
           'have been designated as post beneficiaries. Our goal is to empower abuse fighting plankton and minnows ' \
           'and promote a Steem that is less-friendly to abuse. It is simple. Building abuse fighters equals less ' \
           'abuse.\n\n\n{}'.format(table)
    logging.info('Generated post body')
    benlist = []
    sql = cursor.execute(
        '''SELECT flagger, COUNT(*) * 95 * 10 / (SELECT COUNT(*) FROM steemflagrewards WHERE included == 0 AND 
        flagger IN flaggers) FROM steemflagrewards WHERE flagger in flaggers AND included == 0 GROUP BY flagger ORDER 
        BY flagger;''')
    # Exchange 100 in line 99 with the percentage of the post rewards you want the flaggers to receive
    for q in sql.fetchall():
        benlist.append({'account': q[0], 'weight': int(q[1]) * 10})
    rep = stm.post(
        'Steem Flag Rewards Report - 8 Flagger Post - {}'.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        body, 'steemflagrewards', tags=['steemflagrewards', 'abuse', 'steem', 'steemit', 'flag'], beneficiaries=benlist,
        parse_body=True, self_vote=False, community='busy', app='busy/2.5.4')
    cursor.execute('UPDATE steemflagrewards SET included = 1 WHERE flagger in flaggers;')
    db.commit()
    return construct_authorperm(rep)


def fill_embed(embed: discord.Embed, names: list, template: str):
    """
    Function to add the contents of a list to a discord embed keeping the message size limit in mind
    """
    value = ''
    for n in names:
        if len(value + template.format(n[0])) < 1024:
            value += template.format(n[0])
        else:
            embed.add_field(name='...', value=value, inline=False)
            value = template.format(n[0])
    embed.add_field(name='...', value=value, inline=False)


async def upvote(mention, flag_approval):
    authorperm, flagger, cats, weight, follow_on = mention
    flagger_comment = Comment(authorperm)

    flagger_comment.upvote(weight, config.SFR_NAME)
    await flag_approval.send(f'Successfully voted a mention by {flagger} out of the queue')

    if not follow_on:
        cat_string = ''
        for i in cats.split(', '):
            cat_string += config.CAT_DESCRIPTION[i]
        sfr_comment_body = 'Steem Flag Rewards mention comment has been approved! Thank you for reporting' \
                           'this abuse, @{}. {} This post was submitted via our Discord Community channel.' \
                           'Check us out on the following link!\n[SFR Discord](https://discord.gg/7pqKmg5)'.format(
            flagger, cat_string)
        stm.post(body=sfr_comment_body, reply_identifier=authorperm, community='SFR', parse_body=True,
                 author=config.SFR_NAME)
        await flag_approval.send('Commented on that mention')
    cursor.execute('UPDATE steemflagrewards SET queue = 0 WHERE comment == ?', (authorperm,))
    db.commit()


async def queue_voting(sfr):
    """
    Voting on steemflagrewards mentions one after one once the voting power of the account reached 90%. This maintains a rather staple flagging ROI
    """
    flag_approval = bot.get_channel(config.FLAG_APPROVAL_CHANNEL_ID)
    while True:
        await asyncio.sleep(180)
        if sfr.vp < config.QUEUE_VP:
            continue
        next_queued = cursor.execute(
            '''SELECT comment, flagger, category, weight, followon
            FROM steemflagrewards
            WHERE queue == 1 AND DATETIME('now', '-6.5 days') < created < DATETIME('now', '-6.5 days') 
            ORDER BY created ASC LIMIT 1;''').fetchone()
        if not next_queued:
            continue
        try:
            logging.info(f'Voting on {next_queued[0]}')
            await upvote(next_queued, flag_approval)
        except Exception as e:
            logging.debug(f'Encountered a {e} while executing upvote')
            await flag_approval.send(f'Something went wrong voting for queued mentions. ({e})')

        sfr.refresh()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
bot = Bot(description='SteemFlagRewards Bot', command_prefix='?')


@bot.command()
async def approve(ctx, link):
    """Checks post body for @steemflagrewards mention and https://steemit.com/ and must be in the flag_comment_review
    channel id """
    if ctx.message.channel.id != config.FLAG_APPROVAL_CHANNEL_ID:
        await ctx.send('Send commands in the right channel please.')
        return
    logging.info('Registered command for {} by {}'.format(link, ctx.message.author.name))
    comment_perm = link.split('@')[-1]
    try:
        flaggers_comment = Comment(comment_perm, steem_instance=stm)
    except ContentDoesNotExistsException:
        await ctx.send('Please look at your link again. Could not find the linked comment.')
        return
    flagger = Account(flaggers_comment['author'])
    sfr = Account(config.SFR_NAME, steem_instance=stm)
    if '@steemflagrewards' not in flaggers_comment['body']:
        await ctx.send('Could not find a @steemflagrewards mention. Please check the comment.')
        return
    cats = check_cat(flaggers_comment['body'])
    if not cats:
        await ctx.send('No abuse category found.')
        return
    await ctx.send('Abuse category acknowledged as {}'.format(', '.join(cats)))
    flagged_post = Comment('{}/{}'.format(flaggers_comment['parent_author'], flaggers_comment['parent_permlink']),
                           steem_instance=stm)
    cursor.execute('SELECT * FROM steemflagrewards WHERE comment == ?', (flagged_post.authorperm,))
    if flagged_post['author'] == config.SFR_NAME:  # Check if flag is a follow on flag
        for i in range(2):
            flagged_post = Comment('{}/{}'.format(flagged_post['parent_author'], flagged_post['parent_permlink']),
                                   steem_instance=stm)
        follow_on = True
        await ctx.send('Follow on flag spotted')
    elif cursor.fetchone():
        follow_on = True
        while True:
            flagged_post = Comment(flagged_post['parent_author'] + '/' + flagged_post['parent_permlink'],
                                   steem_instance=stm)
            if cursor.execute('SELECT post FROM steemflagrewards WHERE post == ?',
                              (flagged_post.authorperm,)).fetchall():
                break
    else:
        follow_on = False
        cursor.execute('SELECT post FROM steemflagrewards WHERE post == ?', (flagged_post.authorperm,))
        if cursor.fetchall():
            await ctx.send(
                'There has already been some flagging happenin\' on that post/comment. Please consider using the follow on flag feature if you don\'t make a good comment.')
            follow_on = True
    logging.info(f'Flagged post: {flagged_post.authorperm}')
    weight = 0
    for v in flagged_post['active_votes']:
        if int(v['rshares']) < 0 and v['voter'] == flagger['name']:
            await ctx.send('Downvote confirmed')
            sfrdvote = v

            comment_ROI = config.ROI
            if follow_on is True:
                comment_ROI += config.FOLLOW_ON_ROI
            elif follow_on is False:
                comment_ROI += config.NEW_FLAG_ROI
            else:
                await ctx.send('Something went very wrong. I\'m sorry about the inconvenience.')
            if not cursor.execute('SELECT flagger FROM steemflagrewards WHERE flagger == ?;',
                                  (flagger.name,)).fetchone():
                comment_ROI += config.FIRST_FLAG_ROI

            voting_power = config.QUEUE_VP * 100
            vote_pct = stm.rshares_to_vote_pct(int(abs(int(v['rshares'])) * comment_ROI),  # ROI for the flaggers
                                               steem_power=sfr.sp,
                                               voting_power=voting_power)
            min_vote_pct = stm.rshares_to_vote_pct(0.0245 / stm.get_sbd_per_rshares(),
                                                   steem_power=sfr.sp,
                                                   voting_power=voting_power)
            weight = max(round((vote_pct / 10000) * 100), round((min_vote_pct / 10000) * 100))
    if sfr.get_vote(flaggers_comment):
        await ctx.send('Already voted on this!')
        return
    elif not weight:
        await ctx.send('Apparently, the post wasn\'t flagged!')
        return
    cursor.execute('SELECT comment FROM steemflagrewards WHERE comment == ? LIMIT 1;', (flaggers_comment,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO steemflagrewards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
            flagger.name, flaggers_comment.authorperm, flagged_post.authorperm, ', '.join(cats),
            flaggers_comment['created'], False,
            stm.rshares_to_sbd(sfrdvote['rshares']), True, weight, follow_on))
        db.commit()
    else:
        await ctx.send('Mention has already been approved once.')
    await ctx.send('Queued upvote for later on.')
    q = \
        cursor.execute(
            'SELECT COUNT(DISTINCT flagger) FROM steemflagrewards WHERE included == 0;').fetchone()[
            0]
    await ctx.send(f'Now at {q} out of 9 needed flaggers for a report.')
    if q > 8:
        await ctx.send('Hit flagger threshold. Posting report.')
        r = report()
        msg = f'Sucessfully posted a new report! Check it out! (And upvote it as well :P)\nhttps://steemit.com/{r}'
        await ctx.send(msg)
        postpromo = bot.get_channel(config.POST_PROMOTION_CHANNEL_ID)
        await postpromo.send(msg)
        sfr.claim_reward_balance()


@bot.command()
async def queue(ctx):
    logging.info(f'{ctx.author.name} asked for queue')
    queue = cursor.execute(
        'SELECT DISTINCT comment, post FROM steemflagrewards WHERE queue == 1 ORDER BY created ASC;').fetchall()
    if not queue:
        await ctx.send('No mention in the queue')
        return
    sfr = Account(config.SFR_NAME, steem_instance=stm)
    embeds = []
    queue_embed = discord.Embed(title='@steemflagrewards voting queue',
                                description=f'Next vote will happen in {sfr.get_recharge_time_str(config.QUEUE_VP)}.',
                                color=discord.Color.red())
    queue_embed.add_field(name='Voting Mana', value=round(sfr.vp, 2))
    embeds.append(queue_embed)
    for cnt, mention in enumerate(queue):
        embeds.append(discord.Embed(title=f'Number {cnt+1} in the queue',
                                    description=f'[{mention[0]}](https://steemit.com/{mention[1]}/#{mention[0]})'))
    for e in embeds:
        await ctx.send(embed=e)


@bot.command()
async def clear_queue(ctx):
    """Removes all queued mentions"""
    logging.info(f'{ctx.author.name} sent clear_queue')
    cursor.execute('DELETE FROM steemflagrewards WHERE queue == 1')
    db.commit()
    await ctx.send('Queue has been successfully cleared!')
    return


@bot.command()
async def sdl(ctx, cmd: str, *mode: str):
    """
    Manage the list of the steemit defence league accounts with this command. Use it with ?sdl and one of the following
    """
    logging.info(f'{ctx.author.name} send sdl command with {cmd} ... {mode}')
    if cmd == 'add':
        if ctx.author.id not in config.PERMITTED:
            await ctx.send('You do not have permissions to edit the SDL list.')
            return
        if not mode:
            await ctx.send('Please provide at least one account name.')
            return
        for i in mode:
            if '@' in i:
                i = i.split('@')[-1]
            try:
                acc = Account(i)
            except AccountDoesNotExistsException:
                await ctx.send(f'The account @{i} seems to not exist on the steem blockchain.')
                continue
            if cursor.execute('SELECT name FROM sdl WHERE name == ?', (acc.name,)).fetchall():
                await ctx.send(f'Account @{acc.name} already exists in the list.')
                continue
            if acc['received_vesting_shares'].amount > 0:
                delegation = True
            else:
                delegation = False
            cursor.execute('INSERT INTO sdl VALUES (?, ?, ?)', (acc.name, acc['created'], delegation,))
            await ctx.send(f'Added @{acc.name} to the list.')
        db.commit()
    elif cmd == 'remove':
        if ctx.author.id not in config.PERMITTED:
            await ctx.send('You do not have permissions to edit the SDL list.')
            return
        if not mode:
            await ctx.send('Please provide at least one account name.')
            return
        for i in mode:
            if '@' in i:
                i = i.split('@')[-1]
            if not cursor.execute('SELECT name FROM sdl WHERE name == ?', (i,)).fetchall():
                await ctx.send(f'Could not find an account with the name @{i} in the list.')
                continue
            cursor.execute('DELETE FROM sdl WHERE name == ?', (i,))
            await ctx.send(f'Removed @{i} from the list.')
        db.commit()
    elif cmd == 'list':
        if 'steemd' in mode:
            link = '[{0}](https://steemd.com/@{0})\n'
        elif 'steemit' in mode:
            link = '[{0}](https://steemit.com/@{0})\n'
        else:
            await ctx.send('**Accounts with delegations**')
            second_step = False
            names = cursor.execute('SELECT * FROM sdl ORDER BY delegation DESC, name ASC;').fetchall()
            for n in names:
                if n[2] == 0 and not second_step:
                    await ctx.send('**Accounts without delegations**')
                    second_step = True
                await ctx.send(f'`{n[0]}`')
            return
        delegated = discord.Embed(title='SDL with delegation',
                                  description='A list of Steemit Defence League accounts with a delegation (potentially by @steem)',
                                  color=discord.Color.gold())
        undelegated = discord.Embed(title='SDL without delegation',
                                    description='A list of Steemit Defence League accounts without delegations',
                                    color=discord.Color.blurple())
        names = cursor.execute('SELECT name FROM sdl WHERE delegation == 1 ORDER BY name ASC;').fetchall()
        fill_embed(delegated, names, link)
        names = cursor.execute('SELECT name FROM sdl WHERE delegation == 0 ORDER BY name ASC;').fetchall()
        fill_embed(undelegated, names, link)
        if 'delegated' in mode:
            await ctx.send(embed=delegated)
        elif 'undelegated' in mode:
            await ctx.send(embed=undelegated)
        else:
            await ctx.send(embed=delegated)
            await ctx.send(embed=undelegated)
    elif cmd == 'update':
        for i in cursor.execute('SELECT name FROM sdl WHERE delegation == 1;').fetchall():
            acc = Account(i[0])
            if acc['received_vesting_shares'] == 0:
                cursor.execute('UPDATE sdl SET delegation = 0 WHERE name == ?', i)
                await ctx.send(f'@{i[0]} got his delegation removed. :tada:')
                continue
            await ctx.send(f'@{i[0]} still got his delegation :(')
        db.commit()
    elif cmd == 'file':
        filename = '{}.steemitdefenseleague.txt'.format(datetime.datetime.now().strftime('%Y%m%d'))
        with open(filename, 'w+') as f:
            accounts = cursor.execute('SELECT name FROM sdl ORDER BY name ASC;').fetchall()
            for i in accounts:
                f.write(i[0] + '\n')
        await ctx.send(file=discord.File(filename))
    else:
        await ctx.send('Unknown command.')


@bot.command()
async def status(ctx):
    """Returns the current status of the SFR account."""
    logging.info('Registered status command')
    embed = discord.Embed(title='SFR Status', description='The current status of the SFR bot and account.',
                          color=discord.Color.blue())
    sfr = Account(config.SFR_NAME, steem_instance=stm)
    embed.add_field(name='Bot', value='Up and running', inline=False)
    embed.add_field(name='Flaggers', value='{}/9'.format(cursor.execute(
        'SELECT COUNT(DISTINCT flagger) FROM steemflagrewards WHERE included == 0;').fetchone()[0]), inline=False)
    embed.add_field(name='Mentions', value=cursor.execute(
        'SELECT COUNT(comment) FROM steemflagrewards WHERE included == 0;').fetchone()[0], inline=False)
    tmp = cursor.execute(
        'SELECT SUM(payout), COUNT(payout) FROM steemflagrewards WHERE created > DATETIME(\'now\', \'-7 days\');').fetchone()
    embed.add_field(name='Removed payouts in the last 7 days', value=round(tmp[0], 3), inline=False)
    embed.add_field(name='Total mentions approved in the last 7 days', value=tmp[1])
    embed.add_field(name='Steem Power', value=round(sfr.get_steem_power(), 3), inline=False)
    embed.add_field(name='Voting Mana', value=round(sfr.vp, 2), inline=False)
    embed.add_field(name='VP --> 100%', value=sfr.get_recharge_time_str(100), inline=False)
    embed.add_field(name='Vote Value', value=round(sfr.get_voting_value_SBD(), 3), inline=False)
    embed.add_field(name='Reputation', value=round(sfr.get_reputation(), 3), inline=False)
    embed.add_field(name='Resource Credit %', value=round(sfr.get_rc_manabar()['current_pct'], 1), inline=False)
    post = sfr.get_blog()[0]
    embed.add_field(name='Latest Post',
                    value='[{}](https://steemit.com/@{}/{})'.format(post['title'], post['author'], post['permlink']),
                    inline=False)
    embed.add_field(name='Awesomeness', value='Over 9000', inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def updatenodes(ctx):
    """Updates the nodes using the built in function that is based on hourly run benchmarks. Thanks holger80 for that feature."""
    logging.info('Updating nodes')
    global stm
    n = NodeList()
    n.update_nodes(steem_instance=stm)
    stm = Steem(
        node=n.get_nodes()
    )
    await ctx.send('Updated nodes using @fullnodeupdate.')


@bot.event
async def on_ready():
    logging.info('Started bot!')


def main():
    stm.wallet.unlock(config.WALLET_KEY)
    bot.loop.create_task(queue_voting(Account(config.SFR_NAME)))
    bot.run(config.TOKEN)


if __name__ == '__main__':
    main()
