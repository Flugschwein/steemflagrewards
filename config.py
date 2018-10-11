import os

# Name of the steemflagrewards account
SFR_NAME = 'flugbot'

# Descriptions of all abuse categories
CAT_DESCRIPTION = {
    'bid bot abuse': '\n* bid bot abuse\nYou bought votes to increase the rewards of your post above the value of its content.',
    'collusive voting': '\ndescription placeholder',
    'comment self-vote violation': '\n* comment self-vote violation\nYou left a comment favorable about the post, you didn\'t upvote the post, and upvoted your own comment.',
    'comment spam': '\n* comment spam\nYour comment has been repeated multiple times without regard to the post.',
    'copy/paste': '\n* copy/paste\nYour post mostly contains copied material from a source or stock content and is not your original work.',
    'failure to tag nsfw': '\n* failure to tag nsfw\nYour post should be tagged NSFW when it contains nudity, gore, extreme violence or anything inappropriate for general public viewing.',
    'identity theft': '\n* identity theft\nYou are pretending to be someone you are not.',
    'manipulation': '\ndescription placeholder',
    'phishing': '\n* phishing\nYou are trying to steal account keys, password or credentials.',
    'plagiarism': '\n* plagiarism\nYou are posting content that is not yours by copying it without sourcing or manipulating it to pass plagiarism tools.',
    'post farming': '\ndescription placeholder',
    'scam': '\n* scam\nThis post is a scam, designed to trick or defraud others.',
    'spam': '\n* spam\nYou are repetitively posting the same content or recyling contents after a period of time.',
    'tag abuse': '\n* tag abuse\nYou used tags irrelevant to your content or used the introduceyourself tag more than twice.',
    'tag misuse': '\ndescription placeholder',
    'testing for rewards': '\n* testing for rewards\nYou claimed to be “testing” but did not decline rewards.',
    'threat': '\ndescription placeholder',
    'vote abuse': '\ndescription placeholder',
    'vote farming': '\n* vote farming\nYou\'re churning out content (often low quality), in quick successions with abnormal number and/or upvote size.',
    }

# VP limit for starting queueing
QUEUE_VP = 85

# Steem config variable - if HF > 20 --> 3
STEEM_MIN_REPLY_INTERVAL = 3

# Steem config variable.
STEEM_MIN_VOTE_INTERVAL = 3

# Post Promotion Channel Discord ID
POST_PROMOTION_CHANNEL_ID = 499937015693967360# 426612204717211648

# Flag comment approval Channel Discord ID
FLAG_APPROVAL_CHANNEL_ID = 418780275200360449# 419711548769042432

# SDL List editing permissions
PERMITTED = [405584423950614529,  # Iamstan
             272137261548568576,  # Leonis
             222012811172249600,  # Flugschwein
             398204160538836993,  # Naturicia
             347739387712372747,  # Anthonyadavisii
             102394130176446464,  # TheMarkyMark
             437647893072052233,  # Serylt
             ]

# Local Wallet passphrase
# WALLET_KEY = os.getenv('PASSPHRASE')
WALLET_KEY = 'PASSPHRASE'

# Discord Bot Token
# TOKEN = os.getenv('TOKEN')
TOKEN = 'TOKEN'

# Base ROI for all flags (1.05 --> 5% base ROI)
ROI = 1.05

# ROI addition for the first flag of a user (0.25 --> 25% additional ROI)
FIRST_FLAG_ROI = 0.25

# ROI addition for the first flag of a post (non follow on)
NEW_FLAG_ROI = 0.2

# ROI addition for follow on flags
FOLLOW_ON_ROI = 0.1
