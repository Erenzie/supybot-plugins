###
# Copyright (c) 2016, Eren Zie
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import random
import sqlite3

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Battle')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class Battle(callbacks.PluginRegexp):
    """Attack other users! Thow stuff at them! A plugin for /me battles."""
    threaded = True
    public = True
    unaddressedRegexps = ['attacks', 'throws', 'casts', 'fites', 'slaps']
    
    players = {}
    
    def __init__(self, irc):
        super().__init__(irc)
        
        # sqlite database wooo
        try:
            self.con = sqlite3.connect(conf.supybot.directories.data.dirize("Battle.sqlite"))
            self.cur = self.con.cursor()
        except sqlite3.Error as e:
            print("error opening database: %s" % e)
            # should probably add some code to make a db but i'm L A Z Y
            # i also dunno how to make this be a failure loading the plugin! yay!
    
    #### REGEXES ####
    #regexes = {"attacks":  re.compile(r"^ACTION attacks (.*) with (.*)$"), # vict wep
    #       "stabs":    re.compile(r"^ACTION stabs (.*) with (.*)$"),   # vict wep
    #       "fites":    re.compile(r"^ACTION fites (.*)$"),             # vict
    #       "throws":   re.compile(r"^ACTION throws (.*) at (.*)$"),    # wep vict
    #       "drops":    re.compile(r"^ACTION drops (.*) on (.*)$"),     # wep vict
    #       "thwacks":  re.compile(r"^ACTION thwacks (.*) with (.*)$"), # vict wep
    #       "casts_at": re.compile(r"^ACTION casts (.*) at (.*)$"),     # wep vict
    #       "casts_on": re.compile(r"^ACTION casts (.*) on (.*)$"),     # wep vict
    #       "heals":    re.compile(r"^ACTION heals (.*) with (.*)$")}   # wep vict
    
    def attacks(self, irc, msg, match):
        "^\x01ACTION (attacks|stabs|thwacks) (.*?)(?: with (.*))?\x01$"
        atktype = match.group(1)
        attacker = msg.nick
        victim = match.group(2).strip()
        weapon = match.group(3)
        if not weapon:
            if atktype == 'stabs': # Allow the "stabs with XYZ" part to be omitted
                weapon = "the knife"
            else: # Without a weapon, it is the caller that's injuring the victim.
                weapon = attacker

        self.doAttack(irc, msg, attacker, victim, weapon, atktype)
    
    def throws(self, irc, msg, match):
        "^\x01ACTION throws (.*?) at (.*)\x01$"
        atktype = "throws"
        attacker = msg.nick
        victim = match.group(2)
        weapon = match.group(1)
        self.doAttack(irc, msg, attacker, victim, weapon, atktype)
    
    def casts(self, irc, msg, match):
        "^\x01ACTION (casts|drops) (.*?) (on|at) (.*)\x01$"
        atktype = match.group(1)
        attacker = msg.nick
        victim = match.group(4)
        weapon = match.group(2)
        self.doAttack(irc, msg, attacker, victim, weapon, atktype)
    
    def slaps(self, irc, msg, match):
        "^\x01ACTION slaps (.*?)(?: with (.*))?\x01$"
        atktype = "slaps"
        attacker = msg.nick
        victim = match.group(1)
        weapon = match.group(2)

        if not weapon:
            # Without a weapon, it is the caller that's injuring the victim.
            weapon = random.choice(('the slap', attacker))

        self.doAttack(irc, msg, attacker, victim, weapon, atktype)
    
    def fites(self, irc, msg, match):
        "^\x01ACTION fites (.*)\x01$"
        atktype = "attacks"
        attacker = msg.nick
        victim = match.group(1)
        weapon = "the 1v1 fite irl"
        self.doAttack(irc, msg, attacker, victim, weapon, atktype)
    
    #### END REGEXES ####
    
    def doAttack(self, irc, msg, attacker, victim, weapon, atktype):

        # msg.args[0] represents the channel in the config option lookup
        if not self.registryValue('enabled', msg.args[0]):
            return

        # Make things like "* A stabs B in the feelings" fetch the right victim
        victim = victim.split(' in ')[0]
        # Ditto with "* A throws thorns at B's head"
        victim = victim.split("'")[0]

        # Strip spaces and punctuation from the weapon and victim.
        weapon, victim = map(lambda text: str.strip(text, ',.! '), (weapon, victim))

        batresult = self.doDamage(attacker, victim, weapon, atktype)
        newmsg = self.makeBattleResponse(atktype, victim, weapon, batresult, attacker, irc.state.channels[msg.args[0]].users)
        self.log.info("Battle: %s in %s: %s", msg.nick, msg.args[0], newmsg)
        # lazy hack
        if newmsg == "calls the police":
            irc.reply(newmsg, action=True)
        else:
            irc.reply(newmsg, prefixNick=False)
        if batresult["hp"] == 0:
            irc.reply(self.doRespawn(victim), prefixNick=False)

    def addPlayer(self, name):
        if name in self.players:
            return False
        else:
            self.players[name] = 10000
            return True

    def getHealth(self, name):
        if name in self.players:
            return self.players[name]
        else:
            return False

    def damagePlayer(self, victim, damage):
        if victim not in self.players:
            # add to self.players
            self.addPlayer(victim)
        
        if damage > self.players[victim]:
            self.players[victim] = 0
        else:
            self.players[victim] = self.players[victim] - damage
        
        return self.players[victim]

    def doDamage(self, attacker, victim, weapon, atktype, noFail=False):
        result = {}
        
        if attacker not in self.players:
            self.addPlayer(attacker)
        
        if victim not in self.players:
            self.addPlayer(victim)
        
        # decide if this is a crit or not
        if random.randint(1, 100) > 90:
            isCrit = True
        else:
            isCrit = False
        
        # how much damage should it deal?
        if isCrit:
            damage = random.randint(3000, 10000)
        else:
            damage = random.randint(1, 3000)
        
        if noFail:
            isMiss = False
        else:
            # will this attack miss?
            if random.randint(1, 100) > 90:
                isMiss = True
                damage = 0
            else:
                isMiss = False
        
        nvicthp = self.damagePlayer(victim, damage) # "new victim hp"
        
        if isMiss:
            result["type"] = "miss"
        elif isCrit and nvicthp != 0:
            result["type"] = "crit"
        elif isCrit and nvicthp == 0:
            result["type"] = "fatalCrit"
        elif nvicthp != 0:
            result["type"] = "normal"
        elif nvicthp == 0:
            result["type"] = "fatalNormal"
        else:
            self.log.debug("something broke")
        
        result["dmg"] = damage
        result["hp"] = nvicthp
        
        
        #result["wep"] = self.wepName(weapon, attacker, False) # do capitalisation in makeBattleResponse
        result["wep"] = weapon
        
        return result

    def doRespawn(self, name):
        self.players[name] = 10000
        
        # add to user's death count
        deaths = self.addUserDeath(name)
        
        # https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement/36977549#36977549
        suf = lambda n: "%d%s"%(n,{1:"st",2:"nd",3:"rd"}.get(n if n<20 else n%10,"th"))
        
        lolo = random.randint(1, 2)
        if lolo == 1:
            return "However, through the use of ancient magic rituals, they have been reborn with full health for the {} time.".format(suf(deaths))
        else:
            return "However, thanks to new technology, they have respawned with full health for the {} time.".format(suf(deaths))
    
    #### CREATES BATTLE REPLIES ####
    def makeBattleResponse(self, atktype, victim, weapon, batresult, attacker, users):
        userIsThrown = False # probably a bad hack ayy lmao
        ### ATTACKS, STABS, FITES ###
        if atktype in ["attacks", "stabs", "fites", "slaps"]:
            if batresult["type"] == "miss":
                lolo = random.randint(1, 3)
                if lolo == 1:
                    msg = "MISS!"
                elif lolo == 2:
                    msg = "{} is immune to {}".format(victim, batresult["wep"])
                else:
                    msg = "calls the police"
            elif batresult["type"] == "fatalNormal":
                msg = "{} is fatally injured by {}, taking {} damage. RIP".format(victim, self.wepName(weapon, attacker, False), batresult["dmg"])
            elif batresult["type"] == "fatalCrit":
                msg = "{} is \002CRITICALLY HIT\002 to \002DEATH\002 by {}, taking {} damage! RIP".format(victim, self.wepName(weapon, attacker, False), batresult["dmg"])
            elif batresult["type"] == "normal":
                if batresult["dmg"] > 1500:
                    msg = "{} is tremendously damaged by {}, taking {} damage!".format(victim, self.wepName(weapon, attacker, False), batresult["dmg"], batresult["hp"])
                elif batresult["dmg"] < 200:
                    msg = "{} barely even felt {}, taking {} damage.".format(victim, self.wepName(weapon, attacker, False), batresult["dmg"], batresult["hp"])
                else:
                    msg = "{} takes {} damage from {}.".format(victim, batresult["dmg"], self.wepName(weapon, attacker, False), batresult["hp"])
            elif batresult["type"] == "crit":
                msg = "{} is \002CRITICALLY HIT\002 by {}, taking {} damage!".format(victim, self.wepName(weapon, attacker, False), batresult["dmg"], batresult["hp"])
        
        ### THROWS, DROPS, THWACKS ###
        elif atktype in ["throws", "drops", "thwacks"]:
            if batresult["type"] == "miss":
                # hit some other random person in the channel
                newvictim = random.sample(users, 1)[0]
                self.log.debug("randomly selected new victim is " + newvictim)
                originalvictim = victim
                # def doAttack(self, attacker, victim, weapon, atktype, noFail=False):
                batresult = self.doDamage(attacker, newvictim, weapon, "throws", True)
                msg = "{} missed {} and instead hit {}, dealing {} damage!".format(attacker, originalvictim, newvictim, batresult["dmg"], batresult["hp"])
            elif batresult["type"] in ["fatalNormal", "fatalCrit"]:
                msg = "{} hit {} so hard that they fell over and died, taking {} damage. RIP".format(self.wepName(weapon, attacker, True), victim, batresult["dmg"])
            elif batresult["type"] in ["normal", "crit"]:
                
                # is someone throwing someone at someone?
                if batresult["wep"] in users or batresult["wep"] in ["himself", "herself", "theirself"]:
                    userIsThrown = True
                    # if someone's throwing theirself, use their nick instead of "*self"
                    if batresult["wep"] in ["himself", "herself", "theirself"]:
                        thrownuser = attacker
                    else:
                        thrownuser = batresult["wep"]
                    # add to players if not already
                    if thrownuser not in self.players:
                        self.addPlayer(thrownuser)
                    # and damage them too
                    thrownuserresult = self.doDamage(attacker, thrownuser, weapon, "throws", True)
                        
                if batresult["dmg"] > 1500:
                    # check if plural
                    if batresult["wep"][-1:] == "s":
                        msg = self.wepName(weapon, attacker, True) + " severely injure "
                    else:
                        msg = self.wepName(weapon, attacker, True) + " severely injures "
                    
                    if userIsThrown:
                        msg = msg + "{}, dealing {} damage to both!".format(victim, batresult["dmg"], batresult["hp"])
                    else:
                        msg = msg + "{}, dealing {} damage!".format(victim, batresult["dmg"], batresult["hp"])
                elif batresult["dmg"] < 200:
                    if userIsThrown:
                        msg = "{} barely hit {}, dealing {} damage to both.".format(self.wepName(weapon, attacker, False), victim, batresult["dmg"], batresult["hp"])
                    else:
                        msg = "{} barely hit {}, dealing {} damage.".format(self.wepName(weapon, attacker, False), victim, batresult["dmg"], batresult["hp"])
                else:
                    if batresult["wep"][-1:] == "s":
                        msg = self.wepName(weapon, attacker, True) + " thwack "
                    else:
                        msg = self.wepName(weapon, attacker, True) + " thwacks "
                    
                    if userIsThrown:
                        msg = msg + "{} in the face, dealing {} damage to both.".format(victim, batresult["dmg"], batresult["hp"])
                    else:
                        msg = msg + "{} in the face, dealing {} damage.".format(victim, batresult["dmg"], batresult["hp"])
        
        ### CASTS AT/ON ###
        elif atktype == "casts":
            if batresult["type"] == "miss":
                msg = "You failed at casting..."
            elif batresult["type"] in ["fatalNormal", "fatalCrit"]:
                msg = "{} casts a fatal spell of {} at {}, dealing {} damage. RIP".format(attacker, self.wepName(weapon, attacker, False, False), victim, batresult["dmg"])
            else:
                msg = "{} casts {} at {}, dealing {} damage.".format(attacker, self.wepName(weapon, attacker, False, False), victim, batresult["dmg"], batresult["hp"])
        
        # if not fatal, add current hp to msg
        if batresult["type"] not in ["fatalNormal", "fatalCrit", "miss"]:
            if userIsThrown:
                msg = msg + " {} now has {} HP, and {} now has {} HP.".format(victim, batresult["hp"], thrownuser, thrownuserresult["hp"])
            else:
                msg = msg + " They now have {} HP.".format(batresult["hp"])
        
        return msg
    
    def wepName(self, name, attacker, capitalise, addThe=True):
        name_s = name.partition(" ")

        if name == attacker:
            # The attacker was a person, so it's probably not right to add "the" before it.
            return name
        elif name_s[0] == "a":
            name = name[2:]
        elif name_s[0] == "an" or name_s[0] == "un":
            name = name[3:]
        # check for a/an (or un(e) as requested by Xenthys)
        elif name_s[0] == "une" or name_s[0] == "une":
            name = name[4:]
        
        # check for his/her/their
        if name_s[0] in ["his", "her"]:
            name = name[4:]
            pronounused = True
        elif name_s[0] == "their":
            name = name[6:]
            pronounused = True
        else:
            pronounused = False
        
        # or maybe someone's throwing theirself at someone for some reason
        if name in ["himself", "herself", "theirself"]:
            name = attacker
            return name
        
        # check for "the"
        if name_s[0].lower() != "the":
            # check for 's
            if "'s" not in name:
                # no 's, add the or attacker's name
                if pronounused:
                    name = "{}'s {}".format(attacker, name)
                else:
                    name = "the {}".format(name)
        
        # jk let's remove "the" if we shouldn't be adding the
        if addThe == False and name[:3] == "the":
            name = name[4:]
        
        if capitalise:
            name = name[0].upper() + name[1:]
        
        return name
    
    # And now it's time for fun database stuff
    def getUser(self, nick):
        self.cur.execute("SELECT * FROM users WHERE nick=?", (nick,))
        result = self.cur.fetchone()
        if result == None:
            # user doesn't exist, add them
            self.log.debug("%s does not exist in db, adding" % nick)
            result = self.addUser(nick)
        return result
        
    def addUser(self, nick, gender="o", deaths=0):
        # maybe add a check to see if user already exists?
        self.cur.execute("INSERT INTO users VALUES(?, ?, ?)", (nick, gender, deaths))
        self.con.commit()
        return (nick, gender, deaths)

    def addUserDeath(self, nick):
        # adds +1 to death count
        # this also adds the user if they don't exist!
        userinfo = self.getUser(nick)
        # do i really have to do it like this instead of like $var++;
        deaths = userinfo[2] + 1
        
        self.cur.execute("UPDATE users SET deaths=? WHERE nick=?", (deaths, nick))
        self.con.commit()
        
        return deaths

    def setUserGender(self, nick, gender):
        userinfo = self.getUser(nick)
        
        self.cur.execute("UPDATE users SET gender=? WHERE nick=?", (gender, nick))
        self.con.commit()
        
        return getUser(nick)


Class = Battle


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
