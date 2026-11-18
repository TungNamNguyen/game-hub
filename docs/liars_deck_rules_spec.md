# Liar's Deck — Basic Mode Game Rules & Implementation Specification

> Reference specification for implementing a bluffing card game inspired by Liar's Deck.
> This document describes the **Basic Mode** only. It is written as a machine-friendly game design specification with explicit state, turn flow, validation rules, edge cases, and examples.
>
> **Important:** Use this document as a rules reference, but use original game names, characters, UI, art, sounds, animations, and branding for a new game.

---

## 1. Game Overview

### Objective

Be the **last non-eliminated player**.

Players take turns placing 1–3 cards face down and claiming that all played cards are the current **Table Card**. Players may tell the truth or bluff.

The next player can either:

1. Accept the previous player's claim and play cards of their own.
2. Call **LIAR** and challenge the previous player's claim.

If the challenge is correct, the accused player plays Russian Roulette.
If the challenge is incorrect, the challenger plays Russian Roulette.

A player is eliminated when their Russian Roulette result is **Death**.

---

## 2. Supported Player Count

- Minimum players: **2**
- Maximum players: **4**
- Recommended: **4**

---

## 3. Components

### 3.1 Liar Deck

The main deck contains exactly **20 cards**:

| Card | Quantity |
|---|---:|
| King | 6 |
| Queen | 6 |
| Ace | 6 |
| Joker | 2 |
| **Total** | **20** |

### 3.2 Table Deck

The Table Deck contains:

| Card | Quantity |
|---|---:|
| King | 1 |
| Queen | 1 |
| Ace | 1 |
| **Total** | **3** |

At the beginning of every round, shuffle the Table Deck and reveal one card. That card becomes the Table Card for the entire round.

### 3.3 Revolver Deck

Every player owns an independent hidden Revolver Deck:

| Result | Quantity |
|---|---:|
| Death | 1 |
| Blank | 5 |
| **Total** | **6** |

Before the game begins, every player's Revolver Deck is shuffled independently.

Important:

- The Revolver Deck is persistent across rounds.
- When a player reveals a Blank, that Blank is discarded from their Revolver Deck.
- When a player reveals Death, they are eliminated immediately.
- An eliminated player's Revolver Deck is no longer used.

---

## 4. Core Definitions

### 4.1 Table Card

The revealed card from the Table Deck for the current round.

Possible values:

- `KING`
- `QUEEN`
- `ACE`

### 4.2 Truth Card

A card is a **Truth** during a round when:

```text
card.rank == tableCard
OR
card.rank == JOKER
```

Therefore, Joker is always a Truth regardless of the Table Card.

### 4.3 Lie Card

A card is a **Lie** when:

```text
card.rank != tableCard
AND
card.rank != JOKER
```

### 4.4 Claim

A Claim is the statement made by the active player when they play cards.

Example:

```text
Table Card = KING
Cards played = [KING, JOKER]
Claim = "2 Kings"
```

The claim is truthful because both cards are Truths.

A player may also bluff:

```text
Table Card = KING
Cards played = [QUEEN, ACE]
Claim = "2 Kings"
```

This is a Lie because both played cards are Lies.

---

## 5. Round Setup

At the beginning of every round:

### Step 1 — Choose Table Card

Shuffle the Table Deck and reveal one card.

Example:

```text
Table Deck after shuffle:
[QUEEN, ACE, KING]

Top card revealed:
QUEEN

Current Table Card:
QUEEN
```

### Step 2 — Shuffle Liar Deck

Shuffle all 20 cards.

### Step 3 — Deal Cards

Deal exactly **5 cards to every non-eliminated player**.

For 4 players:

```text
4 players × 5 cards = 20 cards
```

For 3 players:

```text
3 players × 5 cards = 15 cards
5 cards remain unused this round
```

For 2 players:

```text
2 players × 5 cards = 10 cards
10 cards remain unused this round
```

Unused cards must remain unknown to players.

### Step 4 — Determine First Player

- At game start: choose the first player randomly.
- At subsequent rounds:
  - If the previous round ended because a player was caught lying, that **accused player becomes the first player** of the next round if they survived.
  - Otherwise, the first player becomes the **next player in turn order**.

### Step 5 — Start Turn Timer

Each player's turn has a maximum of **30 seconds**.

---

## 6. Turn Order

Turn order is fixed around the table.

For example:

```text
A → B → C → D → A → ...
```

Use one consistent direction (clockwise or counterclockwise) in the implementation.

For a faithful implementation based on the documented rules, use:

```text
A → D → C → B → A
```

if the UI labels players clockwise as A/B/C/D.

The exact visual direction is less important than consistency.

### Eliminated Players

Eliminated players:

- Do not receive turns.
- Do not receive cards in future rounds.
- Remain visible as eliminated until the game ends.

### Players With Zero Cards

If a non-eliminated player has no cards left in their hand during the current round:

- Their turns are skipped for the rest of the round.
- They do not automatically win.

If only one non-eliminated player still has cards in hand, that player is forced to call **LIAR** on the previous player's claim.

---

## 7. Legal Actions During a Turn

On a normal turn, a player can choose exactly one action.

### Action A — Play Cards

The player chooses **1, 2, or 3 cards** from their hand.

Constraints:

```text
1 <= numberOfPlayedCards <= 3
```

The selected cards are placed face down into the central pile.

The player then makes a claim that all played cards are the Table Card.

Examples when `Table Card = KING`:

```text
"1 King"
"2 Kings"
"3 Kings"
```

The player is not required to tell the truth.

After playing cards:

```text
currentPlayer -> next eligible player
```

### Action B — Call LIAR

This action is available only if:

- The player is not the first player of the round.
- There is a previous player's claim to challenge.

The player challenges the immediately previous play.

The challenge does NOT reveal the entire hand.

Only the cards played during the previous turn are revealed.

---

## 8. Important Rule: Maximum 3 Cards Per Turn

A player can play:

- 1 card ✅
- 2 cards ✅
- 3 cards ✅
- 4 cards ❌
- 5 cards ❌

Therefore:

```text
"4 Kings"
```

is **not a legal single-turn claim** in Basic Mode.

Even if a player has enough cards in their hand to represent four Truth cards, they still cannot play four cards in one turn.

---

## 9. Claim Resolution

When a player calls **LIAR**, reveal all cards played in the immediately previous turn.

Evaluate every revealed card against the current Table Card.

### Resolution Algorithm

```pseudo
isTruth(card, tableCard):
    return card.rank == tableCard OR card.rank == JOKER

resolveLiar(previousPlay, tableCard):
    for card in previousPlay.cards:
        if not isTruth(card, tableCard):
            return ACCUSED_LOSES

    return CALLER_LOSES
```

### Rule

- If **at least one revealed card is a Lie**:
  - The previous player was bluffing.
  - The previous player plays Russian Roulette.

- If **all revealed cards are Truths**:
  - The previous player told the truth.
  - The caller was wrong.
  - The caller plays Russian Roulette.

---

## 10. Claim Examples

### Example A — Truth

```text
Table Card: KING
Played Cards: KING + JOKER
Claim: "2 Kings"
```

Evaluation:

```text
KING   -> Truth
JOKER  -> Truth
```

Result:

```text
Claim is TRUE
Caller loses challenge
Caller plays Russian Roulette
```

---

### Example B — Lie

```text
Table Card: KING
Played Cards: KING + QUEEN
Claim: "2 Kings"
```

Evaluation:

```text
KING   -> Truth
QUEEN  -> Lie
```

Result:

```text
Claim is FALSE
Challenge succeeds
Previous player plays Russian Roulette
```

---

### Example C — Complete Bluff

```text
Table Card: ACE
Played Cards: KING + QUEEN + QUEEN
Claim: "3 Aces"
```

All cards are Lies.

Result:

```text
Previous player plays Russian Roulette
```

---

### Example D — Joker

```text
Table Card: QUEEN
Hand contains:
- QUEEN
- JOKER
- KING
- ACE
- ACE
```

The player may truthfully play:

```text
QUEEN + JOKER
Claim = "2 Queens"
```

They may also bluff:

```text
JOKER + KING
Claim = "2 Queens"
```

The second play is still truthful because Joker is a Truth and the King is a Lie, so actually:

```text
QUEEN? -> no
JOKER  -> yes
KING   -> no
```

Therefore `JOKER + KING` is a **Lie**.

---

## 11. Russian Roulette
## Russian Roulette

Each player has 1 revolver containing exactly 6 chambers:

- 1 chamber = DEATH
- 5 chambers = BLANK

At the beginning of the game, randomly shuffle the 6 chamber outcomes once.

Example:

Initial:
[DEATH, BLANK, BLANK, BLANK, BLANK, BLANK]

After randomization:
[BLANK, BLANK, DEATH, BLANK, BLANK, BLANK]

When the player is forced to shoot:

1. Reveal the next chamber.
2. If it is BLANK:
   - Player survives.
   - Remove that chamber permanently.
3. If it is DEATH:
   - Player is eliminated.
4. Do NOT randomize the remaining chambers again.

Example:

Chambers:
[BLANK, BLANK, DEATH, BLANK, BLANK, BLANK]

Shot 1 → BLANK → survive
Remaining:
[BLANK, DEATH, BLANK, BLANK, BLANK]

Shot 2 → DEATH → eliminated

Only the player who loses the Liar challenge performs Russian Roulette.

### Procedure

```pseudo
playRussianRoulette(player):
    result = player.revolverDeck.drawTopCard()

    if result == BLANK:
        discard(result)
        player.survives = true

    if result == DEATH:
        player.eliminated = true
```

### Example

A player's hidden Revolver Deck is:

```text
[Blank, Blank, Death, Blank, Blank, Blank]
```

If their first shot reveals Blank:

```text
Remaining deck:
[Blank, Death, Blank, Blank, Blank]
```

The Blank is gone.

The player now has a higher chance of Death on future shots.

### Probability

If the player still has the complete 6-card deck:

```text
Death probability = 1 / 6 ≈ 16.67%
```

If one Blank has already been discarded:

```text
Death probability = 1 / 5 = 20%
```

Then:

```text
1 / 4 = 25%
1 / 3 ≈ 33.33%
1 / 2 = 50%
1 / 1 = 100%
```

Do not reset the revolver after a Blank unless the game design intentionally adds a custom rule.

---

## 12. End of Round

A round ends immediately after a **LIAR** challenge has been resolved and the required player has completed Russian Roulette.

There are two outcomes:

### Outcome A — Player survives

The player remains in the game.

A new round begins.

### Outcome B — Player dies

The player is eliminated.

A new round begins unless only one player remains alive.

---

## 13. End of Game

The game ends when:

```text
numberOfNonEliminatedPlayers == 1
```

The remaining player wins.

Example:

```text
Players:
A = Alive
B = Eliminated
C = Eliminated
D = Eliminated

Winner = A
```

---

## 14. Full Round Example

Assume four players:

```text
A, B, C, D
```

### Round Setup

```text
Table Card = QUEEN
```

Hands are dealt:

```text
A: Q, K, A, J, K
B: Q, Q, K, A, J
C: K, A, A, Q, K
D: J, K, Q, A, A
```

`J` represents Joker.

First player:

```text
A
```

### Turn 1 — A

A plays:

```text
Q + J
```

Claim:

```text
"2 Queens"
```

Both cards are Truths.

B may challenge, but does not.

### Turn 2 — B

B plays:

```text
Q
```

Claim:

```text
"1 Queen"
```

C does not challenge.

### Turn 3 — C

C plays:

```text
K + A + K
```

Claim:

```text
"3 Queens"
```

This is a Lie.

D calls:

```text
LIAR!
```

The three cards are revealed:

```text
KING -> Lie
ACE  -> Lie
KING -> Lie
```

Therefore C loses the challenge and must play Russian Roulette.

Suppose C reveals Blank.

C survives.

### Round End

The round ends.

The next round begins.

Because C was the player caught lying, C becomes the first player of the new round, assuming C survived.

---

## 15. Full Round Example Where the Caller Is Wrong

Table Card:

```text
ACE
```

Previous player plays:

```text
ACE + JOKER + ACE
```

Claim:

```text
"3 Aces"
```

Next player calls:

```text
LIAR!
```

Reveal:

```text
ACE   -> Truth
JOKER -> Truth
ACE   -> Truth
```

The claim was truthful.

Therefore:

```text
Caller loses
Caller plays Russian Roulette
```

---

## 16. Full Game State Model

A recommended implementation state:

```typescript
GameState {
    gameId: string
    status: "WAITING" | "IN_ROUND" | "GAME_OVER"

    players: Player[]

    turnOrder: PlayerId[]
    currentPlayerIndex: number
    firstPlayerId: PlayerId

    currentRound: number
    tableCard: "KING" | "QUEEN" | "ACE"

    liarDeck: Card[]
    tableDeck: TableCard[]

    centralPile: PlayedCard[]
    previousPlay: PlayedCard | null

    phase:
        "ROUND_SETUP"
        | "PLAYER_TURN"
        | "LIAR_CHALLENGE"
        | "RUSSIAN_ROULETTE"
        | "ROUND_END"
        | "GAME_OVER"

    winnerId: PlayerId | null
}
```

Recommended Player model:

```typescript
Player {
    id: string
    name: string

    hand: Card[]

    revolverDeck: RevolverCard[]

    isAlive: boolean
    hasTimedOut: boolean
}
```

Recommended Card model:

```typescript
type CardRank = "KING" | "QUEEN" | "ACE" | "JOKER"

Card {
    id: string
    rank: CardRank
}
```

Recommended PlayedCard model:

```typescript
PlayedCard {
    playerId: string
    cards: Card[]
    claimRank: "KING" | "QUEEN" | "ACE"
    timestamp: number
}
```

---

## 17. Core Rules as Validation Functions

### Can Play Cards?

```pseudo
canPlayCards(player, selectedCards):
    if player.isAlive == false:
        return false

    if selectedCards.length < 1:
        return false

    if selectedCards.length > 3:
        return false

    if selectedCards are not all in player.hand:
        return false

    return true
```

### Can Call Liar?

```pseudo
canCallLiar(game, player):
    if player.isAlive == false:
        return false

    if game.previousPlay == null:
        return false

    if game.previousPlay.playerId == player.id:
        return false

    return true
```

### Resolve Claim

```pseudo
resolveClaim(cards, tableCard):
    for card in cards:
        if card.rank != tableCard and card.rank != JOKER:
            return {
                truthful: false,
                result: "ACCUSED_PLAYER_LOSES"
            }

    return {
        truthful: true,
        result: "CALLER_LOSES"
    }
```

---

## 18. Recommended State Machine

```text
WAITING
   |
   v
ROUND_SETUP
   |
   v
PLAYER_TURN
   |
   +----------------------+
   |                      |
   | PLAY 1-3             | CALL LIAR
   |                      |
   v                      v
PLAYER_TURN          LIAR_CHALLENGE
                          |
                          v
                  REVEAL_PREVIOUS_PLAY
                          |
                  +-------+-------+
                  |               |
                  | Previous play |
                  | contains Lie  | All Truths
                  v               v
             ACCUSED          CALLER
             ROULETTE         ROULETTE
                  |               |
                  +-------+-------+
                          |
                          v
                    RESOLVE SHOT
                          |
                  +-------+-------+
                  |               |
                Death           Blank
                  |               |
                  v               v
             ELIMINATED       SURVIVES
                  |               |
                  +-------+-------+
                          |
                          v
                    CHECK WINNER
                          |
                    +-----+-----+
                    |           |
                  One          More
                 alive         alive
                    |           |
                    v           v
                GAME_OVER    ROUND_SETUP
```

---

## 19. Important Edge Cases

### Edge Case 1 — First Player Cannot Call Liar

There is no previous play at the beginning of a round.

Therefore:

```text
First player:
- PLAY ✅
- CALL LIAR ❌
```

### Edge Case 2 — Player Has Only 2 Cards

They may play:

```text
1 card ✅
2 cards ✅
3 cards ❌
```

### Edge Case 3 — Player Has 0 Cards

Their turn is skipped.

### Edge Case 4 — Only One Player Has Cards

That player must call LIAR on the previous play.

### Edge Case 5 — Joker

Joker always counts as Truth for the current round.

### Edge Case 6 — A Mixed Play

A play containing even one Lie is considered a Lie.

Example:

```text
Table Card = QUEEN
Played = QUEEN + JOKER + KING
```

Result:

```text
Truth + Truth + Lie = overall Lie
```

### Edge Case 7 — Challenge Result Does Not Depend on Claim Quantity Separately

The system should verify the actual cards played against the current Table Card.

Do NOT implement:

```text
"Player claimed 3 Queens, therefore count the number of Queens in their hand"
```

Instead implement:

```text
Reveal exactly the cards played in the previous turn.
Check every revealed card.
```

### Edge Case 8 — Unused Cards

When fewer than four players are active, undealt cards remain hidden and unused for the round.

### Edge Case 9 — Revolver Is Per Player

Do not share one revolver deck among all players.

Each player has an independent 6-card hidden deck.

### Edge Case 10 — Blank Is Consumed

When a player survives by revealing Blank, that Blank is removed from their revolver deck.

### Edge Case 11 — Death Eliminates Immediately

When a player reveals Death:

```text
isAlive = false
```

They take no further turns.

---

## 20. Timeout Rule

Each turn has a maximum duration of **30 seconds**.

Recommended deterministic implementation for a digital game:

```pseudo
if turnTimer >= 30 seconds:
    autoResolveTimeout(player)
```

The exact timeout punishment should be treated as a **game-design parameter**, because implementations can choose different UX behavior.

For a simple implementation, one possible rule is:

```text
Timeout -> automatically play 1 random legal card
```

Do not silently invent a timeout punishment if exact parity with the reference game is required; make it configurable.

---

## 21. Suggested Server-Authoritative Flow

For multiplayer implementation, make the server authoritative.

### Client sends

```json
{
  "type": "PLAY_CARDS",
  "playerId": "P1",
  "cardIds": ["C07", "C12"],
  "claim": "KING"
}
```

Server validates:

1. It is the player's turn.
2. Player is alive.
3. Selected cards exist in the player's hand.
4. Selected card count is 1–3.
5. Claim matches the current Table Card.
6. Turn timer has not expired.

Server then:

1. Removes selected cards from hand.
2. Adds them to the hidden central pile.
3. Stores the claim.
4. Broadcasts only the number of cards and the claim.
5. Does **not** reveal card identities.
6. Passes turn to the next eligible player.

### Client sends LIAR

```json
{
  "type": "CALL_LIAR",
  "playerId": "P2"
}
```

Server validates:

1. Caller is alive.
2. Caller has a valid turn.
3. There is a previous play.
4. Caller is challenging the immediately previous play.

Server then:

1. Reveals the previous play.
2. Evaluates all cards.
3. Determines loser.
4. Runs that player's revolver.
5. Broadcasts the reveal and result.
6. Checks for game end.
7. Starts a new round if needed.

---

## 22. Information Visibility Rules

This is critical for a bluffing game.

### Public Information

Players may see:

- Current Table Card.
- Player identities.
- Player alive/dead status.
- Number of cards remaining in each player's hand, if the UI exposes this.
- The number of cards played in the previous turn.
- The previous player's claim.
- Revealed cards after a LIAR challenge.
- Roulette result after a player takes the shot.

### Private Information

Only the owner may see:

- Their own hand.
- Their own remaining revolver state, unless the game intentionally exposes probability.

Never send another player's hand to the client.

Never send unrevealed played card identities to other clients.

---

## 23. Example: Complete 4-Player Sequence

```text
Players: A, B, C, D
Table Card: KING
First Player: A
```

### A's Turn

A plays:

```text
[KING, JOKER]
```

Claims:

```text
2 Kings
```

B trusts.

### B's Turn

B plays:

```text
[QUEEN]
```

Claims:

```text
1 King
```

C calls LIAR.

Reveal:

```text
QUEEN -> Lie
```

B loses.

B plays Russian Roulette.

Result:

```text
Blank
```

B survives.

Round ends.

New round begins.

Because B was caught lying, B starts the next round.

---

## 24. Example: Caller Loses

```text
Table Card = ACE
Previous play = [ACE, JOKER]
Claim = "2 Aces"
```

Next player calls LIAR.

Reveal:

```text
ACE   -> Truth
JOKER -> Truth
```

The claim is valid.

Therefore:

```text
Caller -> Russian Roulette
Previous player -> Safe
```

---

## 25. Example: Player Cannot Claim Four Cards

```text
Table Card = QUEEN
Player hand = [Q, Q, JOKER, Q, K]
```

Possible legal play:

```text
[Q, Q, JOKER]
Claim = "3 Queens"
```

Illegal play:

```text
[Q, Q, JOKER, Q]
Claim = "4 Queens"
```

Reason:

```text
Maximum cards per turn = 3
```

The player may still have four Truth-capable cards in hand, but may not put all four into a single play.

---

## 26. Minimum Required Rules for an MVP

If implementing the game in the smallest possible version, implement exactly these mechanics first:

```text
1. 2–4 players
2. 20-card deck: 6K, 6Q, 6A, 2Joker
3. Deal 5 cards/player
4. Random Table Card: K/Q/A
5. Joker always Truth
6. Play 1–3 cards
7. Claim Table Card
8. Next player may Play or Call Liar
9. Reveal only previous play on challenge
10. Any Lie => accused gets Roulette
11. All Truth => caller gets Roulette
12. 6-shot revolver per player: 1 Death + 5 Blank
13. Blank is removed after use
14. Death eliminates player
15. End round after challenge + Roulette
16. Start new round
17. Last alive player wins
18. 30-second turn timer
```

---

## 27. Suggested Config Object

Keep gameplay values configurable rather than hard-coded.

```typescript
const LIARS_DECK_CONFIG = {
    minPlayers: 2,
    maxPlayers: 4,

    cardsPerPlayer: 5,
    minCardsPerPlay: 1,
    maxCardsPerPlay: 3,

    turnTimeSeconds: 30,

    liarDeck: {
        KING: 6,
        QUEEN: 6,
        ACE: 6,
        JOKER: 2,
    },

    tableDeck: {
        KING: 1,
        QUEEN: 1,
        ACE: 1,
    },

    revolver: {
        DEATH: 1,
        BLANK: 5,
    },
};
```

---

## 28. Pseudocode — Main Game Loop

```pseudo
startGame(players):
    validate players between 2 and 4

    for player in players:
        player.isAlive = true
        player.revolverDeck = shuffle([DEATH, BLANK, BLANK, BLANK, BLANK, BLANK])

    firstPlayer = randomAlivePlayer()

    while countAlive(players) > 1:
        startRound(players, firstPlayer)

        while roundIsActive:
            player = getNextEligiblePlayer()

            if onlyOnePlayerHasCards(players):
                player = getOnlyPlayerWithCards()
                resolveLiar(player)
                break

            action = waitForPlayerAction(player, 30 seconds)

            if action.type == PLAY_CARDS:
                applyPlay(action)
                continue

            if action.type == CALL_LIAR:
                loser = resolveLiarChallenge(previousPlay)
                playRussianRoulette(loser)
                roundIsActive = false
                break

        if countAlive(players) <= 1:
            break

        firstPlayer = determineFirstPlayerAfterRound()

    winner = getOnlyAlivePlayer()
    endGame(winner)
```

---

## 29. Pseudocode — Round Setup

```pseudo
startRound(players, firstPlayer):
    tableCard = shuffle([KING, QUEEN, ACE]).drawTop()

    liarDeck = shuffle([
        KING x6,
        QUEEN x6,
        ACE x6,
        JOKER x2
    ])

    for player in alivePlayers(players):
        player.hand = draw(liarDeck, 5)

    centralPile = []
    previousPlay = null
    currentPlayer = firstPlayer
    phase = PLAYER_TURN
```

---

## 30. Pseudocode — Liar Resolution

```pseudo
resolveLiarChallenge(challenger, previousPlay, tableCard):
    reveal(previousPlay.cards)

    containsLie = false

    for card in previousPlay.cards:
        if card.rank != tableCard and card.rank != JOKER:
            containsLie = true
            break

    if containsLie:
        loser = previousPlay.playerId
        firstPlayerNextRound = previousPlay.playerId
    else:
        loser = challenger.id
        firstPlayerNextRound = nextTurnOrderPlayer(previousPlay.playerId)

    return {
        loser,
        firstPlayerNextRound,
        revealedCards: previousPlay.cards,
        containsLie
    }
```

---

## 31. Implementation Checklist

### Rules

- [ ] 2–4 players
- [ ] 20-card Liar Deck
- [ ] K/Q/A/Joker distribution correct
- [ ] 5 cards/player
- [ ] K/Q/A Table Card
- [ ] Joker treated as Truth
- [ ] 1–3 cards per play
- [ ] Claim must be current Table Card
- [ ] Call Liar only against previous play
- [ ] Reveal only challenged cards
- [ ] One Lie is enough to fail the claim
- [ ] Truthful claim makes caller lose

### Turn System

- [ ] 30-second timer
- [ ] First player cannot call Liar
- [ ] Empty-hand players skipped
- [ ] Only player with cards must call Liar
- [ ] Eliminated players skipped

### Revolver

- [ ] One independent revolver deck/player
- [ ] 1 Death + 5 Blank
- [ ] Shuffle at game start
- [ ] Blank is discarded after use
- [ ] Death eliminates player
- [ ] Revolver state persists between rounds

### Round / Game

- [ ] Round ends after challenge + Roulette
- [ ] New Table Card each round
- [ ] Re-deal 5 cards each round
- [ ] New round first-player rule implemented
- [ ] Last alive player wins

### Multiplayer Security

- [ ] Server authoritative
- [ ] Hidden hands are private
- [ ] Hidden played cards are private until challenge
- [ ] Clients cannot submit another player's card IDs
- [ ] All randomization occurs server-side

---

## 32. Source / Verification Notes

This specification is based primarily on a detailed rules reference whose latest revision is dated **2026-08-31**, supplemented by a current Liar's Bar quick-start/reference page and the game's Steam description.

The most important verified Basic Mode rules are:

- 2–4 players.
- 20-card deck: 6 Kings, 6 Queens, 6 Aces, 2 Jokers.
- 5 cards per player each round.
- Table Card is King, Queen, or Ace.
- Jokers count as Truths.
- 1–3 cards can be played per turn.
- A player may either play cards or call LIAR on the immediately previous play.
- A challenged play is revealed and evaluated card-by-card.
- If at least one card is a Lie, the accused player plays Roulette; if all cards are Truths, the caller plays Roulette.
- Each player has a separate 6-card Revolver Deck with 1 Death and 5 Blanks.
- A Blank is discarded; Death eliminates the player.
- A round ends after the challenge is resolved and Roulette is performed.
- The last surviving player wins.

References:

- Liar's Deck detailed rules, latest revision 2026-08-31: https://www.debigare.com/how-to-play-liars-deck-from-liars-bar-full-rules-and-variants/
- Liar's Bar quick start: https://www.liarsbar.net/g/liars-bar-quick-start
- Liar's Bar on Steam: https://store.steampowered.com/app/3097560/Liars_Bar/
