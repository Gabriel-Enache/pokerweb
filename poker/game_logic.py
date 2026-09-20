import random
from itertools import combinations


class Server:
    def __init__(self):
        self._Games = []

    def CreateGame(self, settings):
        if not isinstance(settings, dict):
            return None
        required = ["variant", "buyin", "smallBlind", "bigBlind"]
        for key in required:
            if key not in settings:
                return None
        if settings["variant"] not in ("TexasHoldEm", "Omaha", "FiveCardDraw"):
            return None
        if settings["buyin"] <= 0 or settings["smallBlind"] <= 0 or settings["bigBlind"] <= 0:
            return None
        game = Game(settings)
        self._Games.append(game)
        return game

    def GetGame(self, index):
        if not isinstance(index, int):
            return None
        if 0 <= index < len(self._Games):
            return self._Games[index]
        return None

    def GetGameCount(self):
        return len(self._Games)

    def GetGames(self):
        return list(self._Games)


class Game:
    def __init__(self, settings):
        self._Variant = settings["variant"]
        self._Buyin = settings["buyin"]
        self._SmallBlind = settings["smallBlind"]
        self._BigBlind = settings["bigBlind"]
        self._MaxPlayers = settings.get("maxPlayers", 6)
        self._Password = settings.get("password", "")
        self._Players = []
        self._Rounds = []
        self._CurrentRound = None
        self._DealerButtonIndex = 0
        self._ID = id(self)
        self._ChatLog = []
        self._TimeControl = settings.get("timeControl", 30)

    def GetVariant(self):
        return self._Variant

    def GetBuyin(self):
        return self._Buyin

    def GetSmallBlind(self):
        return self._SmallBlind

    def GetBigBlind(self):
        return self._BigBlind

    def GetMaxPlayers(self):
        return self._MaxPlayers

    def GetPassword(self):
        return self._Password

    def GetPlayers(self):
        return list(self._Players)

    def GetCurrentRound(self):
        return self._CurrentRound

    def GetRounds(self):
        return list(self._Rounds)

    def GetID(self):
        return self._ID

    def GetChatLog(self):
        return list(self._ChatLog)

    def GetTimeControl(self):
        return self._TimeControl

    def AddChat(self, name, message):
        if not isinstance(message, str) or len(message.strip()) == 0:
            return
        self._ChatLog.append({"name": name, "message": message.strip()})
        if len(self._ChatLog) > 200:
            self._ChatLog = self._ChatLog[-200:]

    def AddPlayer(self, name):
        if not isinstance(name, str) or len(name.strip()) == 0:
            return None
        if len(self._Players) >= self._MaxPlayers:
            return None
        player = Player(name.strip(), len(self._Players), self)
        player._chips = self._Buyin
        self._Players.append(player)
        return player

    def RemovePlayer(self, player):
        if not isinstance(player, Player):
            return False
        if player in self._Players:
            self._Players.remove(player)
            return True
        return False

    def NewRound(self):
        if len(self._Players) < 2:
            return None
        rnd = Round(self)
        self._Rounds.append(rnd)
        self._CurrentRound = rnd
        return rnd


class Round:
    def __init__(self, game):
        if not isinstance(game, Game):
            raise TypeError("Round requires a Game instance")

        self._game = game
        self._players = [p for p in game.GetPlayers() if p.GetChips() > 0]
        self._deck = Deck()
        self._deck.Shuffle()
        self._dealer = Dealer()
        self._pots = []
        self._toCall = 0
        self._variant = game.GetVariant()
        self._phase = "preflop"
        self._finished = False
        self._drawComplete = {}  # tracks which players have completed draw phase

        for p in self._players:
            p._cards = []
            p._hand = None
            p._moneyBet = 0
            p._streetBet = 0
            p._totalBet = 0  # cumulative total bet across all streets for side pots
            p._status = "Playing"
            p._action = None
            p._blind = "none"

        self._AssignBlinds()

    def GetPlayers(self):
        return list(self._players)

    def GetPots(self):
        return list(self._pots)

    def GetToCall(self):
        return self._toCall

    def GetDealer(self):
        return self._dealer

    def GetVariant(self):
        return self._variant

    def GetPhase(self):
        return self._phase

    def IsFinished(self):
        return self._finished

    def GetCurrentTurnPlayer(self):
        # during draw phase, find first player who hasn't drawn yet
        if self._phase == "draw":
            for p in self._players:
                if p.GetStatus() == "Playing" and not self._drawComplete.get(p.GetID(), False):
                    return p
            return None

        playing = [p for p in self._players if p.GetStatus() == "Playing" and p.GetAction() is None]
        if playing:
            return playing[0]
        return None

    def _PlayingCount(self):
        """Count players with status Playing (not folded, not all-in)."""
        return sum(1 for p in self._players if p.GetStatus() == "Playing")

    def _AssignBlinds(self):
        if len(self._players) == 0:
            return
        idx = self._game._DealerButtonIndex % len(self._players)
        if len(self._players) == 2:
            sb = idx
            bb = (idx + 1) % len(self._players)
        else:
            sb = (idx + 1) % len(self._players)
            bb = (idx + 2) % len(self._players)

        self._players[sb]._blind = "small"
        self._players[bb]._blind = "big"

        self._ForceBet(self._players[sb], self._game.GetSmallBlind())
        self._ForceBet(self._players[bb], self._game.GetBigBlind())
        self._toCall = self._game.GetBigBlind()
        self._game._DealerButtonIndex += 1

    def _ForceBet(self, player, amount):
        if not isinstance(amount, (int, float)) or amount <= 0:
            return
        actual = min(amount, player.GetChips())
        player._chips -= actual
        player._moneyBet += actual
        player._streetBet += actual
        player._totalBet += actual
        if player._chips == 0:
            player._status = "AllIn"

    def DealHoleCards(self):
        counts = {"TexasHoldEm": 2, "Omaha": 4, "FiveCardDraw": 5}
        n = counts.get(self._variant, 2)
        for p in self._players:
            dealt = self._deck.Deal(n)
            if dealt is not None:
                p._cards = dealt

    def DealCommunity(self, count):
        if not isinstance(count, int) or count <= 0:
            return False
        self._deck.Deal(1)
        cards = self._deck.Deal(count)
        if cards is not None:
            self._dealer._cards.extend(cards)
            return True
        return False

    # discard and draw replacement cards for Five Card Draw
    def DrawCards(self, player, discardIndices):
        if not isinstance(player, Player):
            return False
        if player.GetStatus() != "Playing":
            return False
        if self._phase != "draw":
            return False
        if self._drawComplete.get(player.GetID(), False):
            return False
        if not isinstance(discardIndices, (list, tuple)):
            return False

        indices = sorted(set(i for i in discardIndices if isinstance(i, int) and 0 <= i < len(player.GetCards())), reverse=True)
        if len(indices) > 3:
            indices = indices[:3]
        for i in indices:
            player._cards.pop(i)
        new = self._deck.Deal(len(indices))
        if new is not None:
            player._cards.extend(new)

        self._drawComplete[player.GetID()] = True
        return True

    def IsDrawPhaseComplete(self):
        """Check if all playing players have completed their draw."""
        for p in self._players:
            if p.GetStatus() == "Playing" and not self._drawComplete.get(p.GetID(), False):
                return False
        return True

    def PlayerAction(self, player, action, amount=0):
        if not isinstance(player, Player):
            return False, "Invalid player."
        if not isinstance(action, str):
            return False, "Invalid action type."
        if player not in self._players:
            return False, "Player not in round."
        if player.GetStatus() != "Playing":
            return False, "Cannot act."
        if player.GetAction() is not None:
            return False, "Already acted."

        action = action.lower().strip()

        if action == "fold":
            player._status = "Folded"
            player._action = "Fold"
            return True, "Folded."

        elif action == "check":
            if player._streetBet < self._toCall:
                return False, "Cannot check."
            player._action = "Check"
            return True, "Checked."

        elif action == "call":
            diff = self._toCall - player._streetBet
            if diff <= 0:
                return False, "Nothing to call."
            actual = min(diff, player.GetChips())
            player._chips -= actual
            player._moneyBet += actual
            player._streetBet += actual
            player._totalBet += actual
            player._action = "Call"
            if player._chips == 0:
                player._status = "AllIn"
            return True, f"Called {actual}."

        elif action == "raise":
            if not isinstance(amount, (int, float)) or amount <= 0:
                return False, "Invalid raise amount."
            amount = int(amount)
            newStreetBet = player._streetBet + amount
            if newStreetBet <= self._toCall:
                return False, "Raise too small."
            if amount > player.GetChips():
                return False, "Not enough chips."
            player._chips -= amount
            player._moneyBet += amount
            player._streetBet += amount
            player._totalBet += amount
            self._toCall = player._streetBet
            player._action = "Raise"
            if player._chips == 0:
                player._status = "AllIn"
            # reset other playing players' actions so they must respond
            for p in self._players:
                if p is not player and p.GetStatus() == "Playing":
                    p._action = None
            return True, f"Raised {amount}."

        elif action == "allin":
            if player.GetChips() <= 0:
                return False, "No chips."
            amount = player.GetChips()
            player._chips = 0
            player._moneyBet += amount
            player._streetBet += amount
            player._totalBet += amount
            player._status = "AllIn"
            if player._streetBet > self._toCall:
                self._toCall = player._streetBet
                player._action = "Raise"
                for p in self._players:
                    if p is not player and p.GetStatus() == "Playing":
                        p._action = None
            else:
                player._action = "Call"
            return True, f"All in {player._totalBet}."

        return False, "unknown action"

    def ResetStreet(self):
        self._toCall = 0
        for p in self._players:
            p._streetBet = 0
            if p.GetStatus() == "Playing":
                p._action = None

    def IsStreetComplete(self):
        for p in self._players:
            if p.GetStatus() == "Playing" and p.GetAction() is None:
                return False
        return True

    def ActiveCount(self):
        return sum(1 for p in self._players if p.GetStatus() in ("Playing", "AllIn"))

    def _NeedsBetting(self):
        """Check if there are enough playing (non-allin) players to need a betting round."""
        playing = sum(1 for p in self._players if p.GetStatus() == "Playing")
        return playing >= 2

    def AdvancePhase(self):
        if self._finished:
            return None

        # if only one non-folded player remains, finish immediately
        if self.ActiveCount() <= 1:
            return self.Finish()

        if self._phase == "draw":
            # for draw phase, check if all draws are complete
            if self.IsDrawPhaseComplete():
                self.ResetStreet()
                self._phase = "postdraw"
                # if no betting needed (all but one all-in), skip to finish
                if not self._NeedsBetting():
                    return self.Finish()
                return None
            else:
                return None

        if not self.IsStreetComplete():
            return None

        if self._variant in ("TexasHoldEm", "Omaha"):
            phases = ["preflop", "flop", "turn", "river"]
            currentIdx = phases.index(self._phase) if self._phase in phases else -1

            if self._phase == "preflop":
                self.ResetStreet()
                self.DealCommunity(3)
                self._phase = "flop"
            elif self._phase == "flop":
                self.ResetStreet()
                self.DealCommunity(1)
                self._phase = "turn"
            elif self._phase == "turn":
                self.ResetStreet()
                self.DealCommunity(1)
                self._phase = "river"
            elif self._phase == "river":
                return self.Finish()

            # if no betting possible (0 or 1 playing player), auto-advance through remaining phases
            if not self._NeedsBetting():
                return self._AutoAdvance()

        elif self._variant == "FiveCardDraw":
            if self._phase == "preflop":
                self._phase = "draw"
                self._drawComplete = {}
                # mark folded/allin players as draw complete
                for p in self._players:
                    if p.GetStatus() != "Playing":
                        self._drawComplete[p.GetID()] = True
                # if all players already completed (all folded/allin), skip draw
                if self.IsDrawPhaseComplete():
                    self.ResetStreet()
                    self._phase = "postdraw"
                    if not self._NeedsBetting():
                        return self.Finish()
                return None
            elif self._phase == "postdraw":
                return self.Finish()

        return None

    def _AutoAdvance(self):
        """auto advances through remaining community card phases when no betting is possible"""
        if self._variant in ("TexasHoldEm", "Omaha"):
            while self._phase != "river" and not self._finished:
                if self._phase == "flop":
                    self.DealCommunity(1)
                    self._phase = "turn"
                elif self._phase == "turn":
                    self.DealCommunity(1)
                    self._phase = "river"
                elif self._phase == "preflop":
                    self.DealCommunity(3)
                    self._phase = "flop"
            return self.Finish()
        elif self._variant == "FiveCardDraw":
            return self.Finish()

    def BuildHands(self):
        for p in self._players:
            if p.GetStatus() == "Folded":
                p._hand = Hand(([], 0, 0))
                continue

            if self._variant == "TexasHoldEm":
                allCards = p.GetCards() + self._dealer.GetCards()
                p._hand = self._BestFive(allCards)

            elif self._variant == "Omaha":
                """ for omaha just run makehand but with all combinations
                including 2 player cards and 3 dealer cards
                and pick out the best hand from those"""
                best = None
                for hole2 in combinations(p.GetCards(), 2):
                    for comm3 in combinations(self._dealer.GetCards(), 3):
                        five = list(hole2) + list(comm3)
                        h = self._BestFive(five)
                    
                        if best is None or h.Power() > best.Power():
                            best = h
                p._hand = best

            elif self._variant == "FiveCardDraw":
                p._hand = self._BestFive(p.GetCards())

    def _BestFive(self, cards):
        if not cards or len(cards) == 0:
            return Hand(([], 0, 0))
        if len(cards) <= 5:
            return Hand(Deck(list(cards)).MakeHand())
        best = None
        for combo in combinations(cards, 5):
            h = Hand(Deck(list(combo)).MakeHand())
            if best is None or h.Power() > best.Power():
                best = h
        return best

    def _BuildSidePots(self):
        # build side pots based on each player's total bet across all streets
        # get 2 lists, one with how many players each player beats, and one sorted by how much money each player has in
        nonFolded = [p for p in self._players if p.GetStatus() != "Folded"]
        allPlayers = list(self._players)

        # sort by totalBet ascending
        sortedByBet = sorted(allPlayers, key=lambda p: p._totalBet)

        self._pots = []
        previousCap = 0

        for capPlayer in sortedByBet:
            cap = capPlayer._totalBet
            if cap <= previousCap:
                continue

            # build sub-pot: each player contributes min(theirTotal, cap) - previousCap
            subPotAmount = 0
            eligible = []

            for p in allPlayers:
                contribution = min(p._totalBet, cap) - min(p._totalBet, previousCap)
                if contribution > 0:
                    subPotAmount += contribution
                # eligible if not folded and totalBet >= cap
                if p.GetStatus() != "Folded" and p._totalBet >= cap:
                    eligible.append(p)

            if subPotAmount > 0:
                pot = Pot(eligible)
                pot._amount = subPotAmount
                self._pots.append(pot)

            previousCap = cap

    def DistributeMoney(self):
        active = [p for p in self._players if p.GetStatus() != "Folded"]

        if len(active) == 0:
            return {}

        # everyone else folded, winner takes all
        if len(active) == 1:
            totalBet = sum(p._totalBet for p in self._players)
            active[0]._chips += totalBet
            return {active[0]: totalBet}

        # build proper side pots from totalBet
        self._BuildSidePots()

        winnings = {p: 0 for p in self._players}

        for pot in self._pots:
            if pot.GetAmount() == 0:
                continue
            eligible = [p for p in pot.GetEligible() if p.GetStatus() != "Folded"]
            if not eligible:
                eligible = active
            if not eligible:
                continue

            # correctly assigns hands a power value such that it is greater than all worse hands' power values
            bestPower = max(p.GetHand().Power() for p in eligible)
            winners = [p for p in eligible if p.GetHand().Power() == bestPower]

            # distributes integer amount to players who won the sub pot
            share = pot.GetAmount() // len(winners)
            # distributes remainder amount of chips to a random winner
            # (so no chips are lost, and all chips are integer) - conservation of chips
            remainder = pot.GetAmount() % len(winners)

            for w in winners:
                w._chips += share
                winnings[w] += share

            # includes a way of randomly deciding indivisible pots
            # so that chips are not created or destroyed
            if remainder > 0:
                lucky = random.choice(winners)
                lucky._chips += remainder
                winnings[lucky] += remainder

            pot._amount = 0

        return winnings

    def Finish(self):
        if self._finished:
            return {}
        self.BuildHands()
        result = self.DistributeMoney()
        self._finished = True
        self._phase = "showdown"
        return result


class Pot:
    def __init__(self, eligible):
        if not isinstance(eligible, list):
            eligible = []
        self._amount = 0
        self._eligible = list(eligible)

    def GetAmount(self):
        return self._amount

    def GetEligible(self):
        return list(self._eligible)


class Dealer:
    def __init__(self):
        self._cards = []

    def GetCards(self):
        return list(self._cards)


class Player:
    def __init__(self, name, pid, game):
        if not isinstance(name, str) or len(name.strip()) == 0:
            raise ValueError("Player name must be a non-empty string")
        if not isinstance(pid, int) or pid < 0:
            raise ValueError("Player ID must be a non-negative integer")
        if not isinstance(game, Game):
            raise TypeError("Player requires a Game instance")

        self._Name = name.strip()
        self._ID = pid
        self._game = game
        self._chips = 0
        self._cards = []
        self._hand = None
        self._status = "Playing"
        self._action = None
        self._moneyBet = 0
        self._streetBet = 0
        self._totalBet = 0
        self._blind = "none"
        self._emoji = ""
        self._sid = None

    def GetName(self):
        return self._Name

    def GetID(self):
        return self._ID

    def GetGame(self):
        return self._game

    def GetChips(self):
        return self._chips

    def GetCards(self):
        return list(self._cards)

    def GetHand(self):
        return self._hand

    def GetStatus(self):
        return self._status

    def GetAction(self):
        return self._action

    def GetMoneyBet(self):
        return self._moneyBet

    def GetStreetBet(self):
        return self._streetBet

    def GetTotalBet(self):
        return self._totalBet

    def GetBlind(self):
        return self._blind

    def GetEmoji(self):
        return self._emoji

    def SetEmoji(self, emoji):
        if isinstance(emoji, str):
            self._emoji = emoji

    def GetSid(self):
        return self._sid

    def SetSid(self, sid):
        self._sid = sid


class Deck:
    def __init__(self, cards=None):
        if cards is None:
            Ranks = "AKQJT98765432"
            Suits = "scdh"
            self._cards = [Card(r, s) for r in Ranks for s in Suits]
        else:
            if not isinstance(cards, list):
                raise TypeError("Cards must be a list")
            self._cards = list(cards)
        self._remaining = len(self._cards)

    def Deal(self, amount):
        if not isinstance(amount, int) or amount <= 0:
            return None
        if self._remaining < amount:
            return None
        self._remaining -= amount
        dealt = self._cards[-amount:]
        self._cards = self._cards[:-amount]
        return dealt

    def Shuffle(self):
        random.shuffle(self._cards)

    def GetRemaining(self):
        return self._remaining

    def MakeHand(self):
        if not self._cards or len(self._cards) == 0:
            return ([], 0, 0)

        strength = 0  # hand strength, beats hands of lower strengths
        substrength = 0  # substrength, beats same hand of lower substrength
        bestmadehand = None

        straightOrder = "A23456789TJQKA"

        # flushcheck (including straight flush)
        madesuit = None  # suit which made a flush
        for suit in "scdh":  # going through each individual suit
            cardsuits = list(card.suit for card in self._cards)
            if cardsuits.count(suit) >= 5:
                madesuit = suit
                break  # can break as made hands will at most contain 9 cards (in the case of 4 card hands), so only 1 suit flush is possible.
        if madesuit is not None:
            flushcards = list(filter(lambda card: card.suit == madesuit, self._cards))  # filters out so only cards of the flush suit remain

            # checking for straightflush
            for start in range(len(straightOrder) - 4):
                if set(rank for rank in straightOrder[start:start + 5]).issubset(set(card.rank for card in flushcards)):
                    if strength <= 9:
                        strength = 9  # strength of straight flush
                        substrength = start
                        bestmadehand = list(Card(rank, madesuit) for rank in straightOrder[start:start + 5][::-1])  # generates made straight flush hand

            # checking for just flush if non straightflush
            if strength != 9:
                sortedflush = sorted(flushcards, key=lambda card: (12 - card.Value()))[0:5]
                strength = 6
                substrength = 0
                for count, card in enumerate(sortedflush):
                    substrength += 12 ** (-count) * card.Value()  # cards (ranks) into base 12 to create unique & corresponding strength values
                bestmadehand = sortedflush

        # straight check
        if strength < 6:
            for start in range(len(straightOrder) - 4):
                if set(rank for rank in straightOrder[start:start + 5]).issubset(set(card.rank for card in self._cards)):  # straight occurred
                    possibleCards = list(filter(lambda card: card.rank in straightOrder[start:start + 5], self._cards))
                    sortedPossible = sorted(possibleCards, key=lambda card: -straightOrder[start:start + 5].index(card.rank))  # cards which are part of the straight, in order
                    bestmadehand = []
                    for card in sortedPossible:
                        if card.rank not in (incard.rank for incard in bestmadehand):
                            bestmadehand.append(card)  # takes one of each rank to make a 5 card straight
                    if len(bestmadehand) >= 5:
                        bestmadehand = bestmadehand[:5]
                        strength = 5
                        substrength = start

        # repeat rank hands check
        if strength < 9:
            cardRanks = list(card.rank for card in self._cards)  # list of only cards's ranks
            cardsByRank = (sorted(self._cards, key=lambda card: 12 - card.Value()))  # available cards ordered by rank
            cardsByAmount = sorted(self._cards, key=lambda card: -cardRanks.count(card.rank) - card.Value() * 10e-3)  # cards ordered by amount of its rank then by highest rank first
            mostProminent = cardsByAmount[0]  # highest rank card which appears the most
            if len(cardsByAmount) > cardRanks.count(mostProminent.rank):
                secondProminent = cardsByAmount[cardRanks.count(mostProminent.rank):][0]  # highest rank card which appears 2nd most (useful for distinguishing full house/ 3OaK, two pair & pair)
            else:
                secondProminent = None

            if cardRanks.count(mostProminent.rank) == 4:  # FoAK check
                card5 = list(filter(lambda card: card.rank != mostProminent.rank, cardsByRank))[0]  # highest other card is the first index as FoAK cards are removed
                strength = 8
                substrength = 12 * mostProminent.Value() + card5.Value()  # unique substrength using base 12 with prominent rank + highest other rank

                bestmadehand = cardsByAmount[0:4]  # FoAK rank
                bestmadehand.append(card5)  # high card rank

            elif cardRanks.count(mostProminent.rank) == 3:  # full house or 3oAK

                if secondProminent and cardRanks.count(secondProminent.rank) > 1:  # full house has occurred
                    strength = 7
                    substrength = mostProminent.Value() + secondProminent.Value() * 12 ** -1

                    bestmadehand = cardsByAmount[0:5]  # with 7 cards, last 4 can only have 2 pairs of 2 cards, so, the first 5 cards will be ordered

                elif strength < 5 and secondProminent and cardRanks.count(secondProminent.rank) == 1:  # 3oAK has occurred
                    strength = 4
                    substrength = mostProminent.Value() + cardsByAmount[3].Value() * 12 ** -1 + cardsByAmount[4].Value() * 12 ** -2

                    bestmadehand = cardsByAmount[0:5]

            elif cardRanks.count(mostProminent.rank) == 2 and strength < 4:  # two pair or pair has occurred

                if secondProminent and cardRanks.count(secondProminent.rank) == 2:  # two pair has occurred
                    card5 = list(filter(lambda card: (card.rank != mostProminent.rank and card.rank != secondProminent.rank), cardsByRank))[0]  # removing 2 pair cards to find fifth card
                    strength = 3
                    substrength = mostProminent.Value() + secondProminent.Value() * 12 ** -1 + card5.Value() * 12 ** -2

                    bestmadehand = cardsByAmount[0:4]
                    bestmadehand.append(card5)

                else:  # pair has occurred (first 5 cardsByAmount are made hand)
                    strength = 2
                    substrength = mostProminent.Value() + sum(card.Value() * 12 ** -(1 + i) for (i, card) in enumerate(cardsByAmount[2:5]))

                    bestmadehand = cardsByAmount[0:5]

            elif cardRanks.count(mostProminent.rank) == 1 and strength == 0:  # highcard has occurred (no repeats) so first 5 cards are best hand
                strength = 1
                substrength = sum(card.Value() * 12 ** -i for (i, card) in enumerate(cardsByAmount[0:5]))

                bestmadehand = cardsByAmount[0:5]

        if bestmadehand is None:
            bestmadehand = sorted(self._cards, key=lambda c: -c.Value())[:5]
            strength = 1
            substrength = sum(c.Value() * 12 ** -i for i, c in enumerate(bestmadehand))

        return (bestmadehand, strength, substrength)


class Card:
    def __init__(self, rank, suit):
        if not isinstance(rank, str) or rank not in "23456789TJQKA":
            raise ValueError(f"Invalid rank: {rank}")
        if not isinstance(suit, str) or suit not in "scdh":
            raise ValueError(f"Invalid suit: {suit}")
        self._rank = rank
        self._suit = suit

    @property
    def rank(self):
        return self._rank

    @property
    def suit(self):
        return self._suit

    def Value(self):
        return "23456789TJQKA".index(self._rank)

    def __str__(self):
        return f"{self._rank}{self._suit}"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self._rank == other._rank and self._suit == other._suit

    def __hash__(self):
        return hash((self._rank, self._suit))


class Hand:
    def __init__(self, makehand):
        if not isinstance(makehand, tuple) or len(makehand) != 3:
            raise ValueError("Hand requires a 3-tuple from MakeHand")
        self._cards = makehand[0] if makehand[0] is not None else []
        self._strength = makehand[1]
        self._substrength = makehand[2]

    @property
    def cards(self):
        return list(self._cards)

    @property
    def strength(self):
        return self._strength

    @property
    def substrength(self):
        return self._substrength

    def Power(self):
        return self._strength * 13 + self._substrength

    def HandType(self):
        handTypes = {
            0: "No Hand", 1: "High Card", 2: "Pair", 3: "Two Pair",
            4: "Three Of A Kind", 5: "Straight", 6: "Flush",
            7: "Full House", 8: "Four Of A Kind", 9: "Straight Flush"
        }
        return handTypes.get(self._strength, "Unknown")