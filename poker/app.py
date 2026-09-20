from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from game_logic import Server
import time
import threading

app = Flask(__name__)
app.secret_key = "poker_secret_key_change_this"
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)

server = Server()

connected_players = {}
active_timers = {}


def get_game_state(game, player_sid=None):
    rnd = game.GetCurrentRound()
    players_data = []

    for i, p in enumerate(game.GetPlayers()):
        pdata = {
            "name": p.GetName(),
            "id": p.GetID(),
            "chips": p.GetChips(),
            "status": p.GetStatus(),
            "action": p.GetAction(),
            "streetBet": p.GetStreetBet(),
            "totalBet": p.GetTotalBet(),
            "blind": p.GetBlind(),
            "emoji": p.GetEmoji(),
            "seatIndex": i,
            "cards": [],
            "hand": None
        }

        if rnd and not rnd.IsFinished():
            if p.GetSid() == player_sid:
                pdata["cards"] = [str(c) for c in p.GetCards()]
            else:
                pdata["cards"] = ["??" for _ in p.GetCards()]
        elif rnd and rnd.IsFinished():
            if p.GetStatus() != "Folded":
                pdata["cards"] = [str(c) for c in p.GetCards()]
                if p.GetHand():
                    pdata["hand"] = {
                        "type": p.GetHand().HandType(),
                        "power": p.GetHand().Power(),
                        "cards": [str(c) for c in p.GetHand().cards]
                    }
            else:
                pdata["cards"] = []

        players_data.append(pdata)

    round_data = None
    if rnd:
        currentTurn = rnd.GetCurrentTurnPlayer()
        round_data = {
            "phase": rnd.GetPhase(),
            "toCall": rnd.GetToCall(),
            "pot": sum(p.GetTotalBet() for p in rnd.GetPlayers()),
            "community": [str(c) for c in rnd.GetDealer().GetCards()],
            "finished": rnd.IsFinished(),
            "currentTurn": currentTurn.GetName() if currentTurn else None,
            "currentTurnId": currentTurn.GetID() if currentTurn else None
        }

    return {
        "variant": game.GetVariant(),
        "buyin": game.GetBuyin(),
        "smallBlind": game.GetSmallBlind(),
        "bigBlind": game.GetBigBlind(),
        "maxPlayers": game.GetMaxPlayers(),
        "timeControl": game.GetTimeControl(),
        "players": players_data,
        "round": round_data,
        "chat": game.GetChatLog()[-50:]
    }


def get_lobby_list():
    games = []
    for i, g in enumerate(server.GetGames()):
        games.append({
            "index": i,
            "variant": g.GetVariant(),
            "buyin": g.GetBuyin(),
            "smallBlind": g.GetSmallBlind(),
            "bigBlind": g.GetBigBlind(),
            "players": len(g.GetPlayers()),
            "maxPlayers": g.GetMaxPlayers(),
            "hasPassword": len(g.GetPassword()) > 0,
            "timeControl": g.GetTimeControl()
        })
    return games


def broadcast_lobby():
    socketio.emit("lobby_list", get_lobby_list())


def broadcast_state(game_index):
    game = server.GetGame(game_index)
    if game is None:
        return
    for p in game.GetPlayers():
        if p.GetSid():
            state = get_game_state(game, p.GetSid())
            socketio.emit("game_state", state, room=p.GetSid())


def start_turn_timer(game_index):
    game = server.GetGame(game_index)
    if game is None:
        return
    rnd = game.GetCurrentRound()
    if rnd is None or rnd.IsFinished():
        return

    current = rnd.GetCurrentTurnPlayer()
    if current is None:
        return

    timer_key = f"{game_index}_{current.GetID()}"

    if timer_key in active_timers:
        active_timers[timer_key]["cancelled"] = True

    timer_state = {"cancelled": False}
    active_timers[timer_key] = timer_state
    time_limit = game.GetTimeControl()

    socketio.emit("timer_start", {
        "playerId": current.GetID(),
        "timeLimit": time_limit
    }, room=f"game_{game_index}")

    def timer_expire():
        if timer_state["cancelled"]:
            return
        rnd2 = game.GetCurrentRound()
        if rnd2 and not rnd2.IsFinished():
            curr = rnd2.GetCurrentTurnPlayer()
            if curr and curr.GetID() == current.GetID():
                if rnd2.GetPhase() == "draw":
                    rnd2.DrawCards(curr, [])
                    check_draw_advance(game_index)
                else:
                    rnd2.PlayerAction(curr, "fold")
                    check_advance(game_index)

    timer = threading.Timer(time_limit, timer_expire)
    timer.daemon = True
    timer.start()


def cancel_timer(game_index, player_id):
    timer_key = f"{game_index}_{player_id}"
    if timer_key in active_timers:
        active_timers[timer_key]["cancelled"] = True


def check_advance(game_index):
    game = server.GetGame(game_index)
    if game is None:
        return
    rnd = game.GetCurrentRound()
    if rnd is None or rnd.IsFinished():
        broadcast_state(game_index)
        return

    if rnd.ActiveCount() <= 1:
        rnd.Finish()
        broadcast_state(game_index)
        return

    if rnd.IsStreetComplete():
        result = rnd.AdvancePhase()
        if result is not None:
            broadcast_state(game_index)
            return
        if rnd.IsFinished():
            broadcast_state(game_index)
            return

    broadcast_state(game_index)

    if not rnd.IsFinished():
        current = rnd.GetCurrentTurnPlayer()
        if current is not None:
            start_turn_timer(game_index)


def check_draw_advance(game_index):
    game = server.GetGame(game_index)
    if game is None:
        return
    rnd = game.GetCurrentRound()
    if rnd is None or rnd.IsFinished():
        broadcast_state(game_index)
        return

    if rnd.IsDrawPhaseComplete():
        result = rnd.AdvancePhase()
        if result is not None:
            broadcast_state(game_index)
            return
        if rnd.IsFinished():
            broadcast_state(game_index)
            return

    broadcast_state(game_index)

    if not rnd.IsFinished():
        current = rnd.GetCurrentTurnPlayer()
        if current is not None:
            start_turn_timer(game_index)


# ROUTES

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/lobby")
def lobby():
    if "name" not in session:
        return redirect(url_for("index"))
    return render_template("lobby.html", name=session["name"])


@app.route("/table/<int:game_index>")
def table(game_index):
    if "name" not in session:
        return redirect(url_for("index"))
    game = server.GetGame(game_index)
    if game is None:
        return redirect(url_for("lobby"))
    return render_template("table.html", name=session["name"], game_index=game_index)


@app.route("/set_name", methods=["POST"])
def set_name():
    name = request.form.get("name", "").strip()
    if len(name) == 0:
        return redirect(url_for("index"))
    session["name"] = name
    return redirect(url_for("lobby"))


# SOCKET EVENTS

@socketio.on("connect")
def on_connect():
    pass


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    if sid in connected_players:
        info = connected_players[sid]
        leave_room(f"game_{info['game_index']}")
        del connected_players[sid]


@socketio.on("get_lobbies")
def on_get_lobbies():
    emit("lobby_list", get_lobby_list())


@socketio.on("create_game")
def on_create_game(data):
    name = session.get("name", None)
    if not name:
        emit("error", {"message": "Not logged in."})
        return

    try:
        settings = {
            "variant": data.get("variant", "TexasHoldEm"),
            "buyin": int(data.get("buyin", 1000)),
            "smallBlind": int(data.get("smallBlind", 5)),
            "bigBlind": int(data.get("bigBlind", 10)),
            "maxPlayers": int(data.get("maxPlayers", 6)),
            "password": data.get("password", ""),
            "timeControl": int(data.get("timeControl", 30))
        }
    except (ValueError, TypeError):
        emit("error", {"message": "Invalid game settings."})
        return

    game = server.CreateGame(settings)
    if game is None:
        emit("error", {"message": "Invalid game settings."})
        return

    game_index = server.GetGameCount() - 1
    emit("game_created", {"game_index": game_index})
    broadcast_lobby()


@socketio.on("join_game")
def on_join_game(data):
    name = session.get("name", None)
    if not name:
        emit("error", {"message": "Not logged in."})
        return

    game_index = data.get("game_index")
    if not isinstance(game_index, int):
        try:
            game_index = int(game_index)
        except (ValueError, TypeError):
            emit("error", {"message": "Invalid game index."})
            return

    password = data.get("password", "")
    game = server.GetGame(game_index)

    if game is None:
        emit("error", {"message": "Game not found."})
        return

    if game.GetPassword() and game.GetPassword() != password:
        emit("error", {"message": "Wrong password."})
        return

    sid = request.sid

    # check if player already in game (reconnect)
    for p in game.GetPlayers():
        if p.GetName() == name:
            p.SetSid(sid)
            connected_players[sid] = {
                "game_index": game_index,
                "player_index": p.GetID(),
                "name": name
            }
            join_room(f"game_{game_index}")
            state = get_game_state(game, sid)
            emit("game_state", state)
            return

    # add new player
    player = game.AddPlayer(name)
    if player is None:
        emit("error", {"message": "Game is full."})
        return

    player.SetSid(sid)
    connected_players[sid] = {
        "game_index": game_index,
        "player_index": player.GetID(),
        "name": name
    }

    join_room(f"game_{game_index}")

    # send state to the joining player immediately
    state = get_game_state(game, sid)
    emit("game_state", state)

    # broadcast updated state to all other players
    broadcast_state(game_index)
    broadcast_lobby()


@socketio.on("request_state")
def on_request_state(data):
    """Client can request current state at any time."""
    name = session.get("name", None)
    if not name:
        emit("error", {"message": "Not logged in."})
        return

    sid = request.sid

    if sid in connected_players:
        info = connected_players[sid]
        game = server.GetGame(info["game_index"])
        if game:
            state = get_game_state(game, sid)
            emit("game_state", state)
            return

    game_index = data.get("game_index")
    if game_index is None:
        return
    if not isinstance(game_index, int):
        try:
            game_index = int(game_index)
        except (ValueError, TypeError):
            return

    game = server.GetGame(game_index)
    if game is None:
        return

    # find player in game
    for p in game.GetPlayers():
        if p.GetName() == name:
            p.SetSid(sid)
            connected_players[sid] = {
                "game_index": game_index,
                "player_index": p.GetID(),
                "name": name
            }
            join_room(f"game_{game_index}")
            state = get_game_state(game, sid)
            emit("game_state", state)
            return


@socketio.on("start_round")
def on_start_round():
    sid = request.sid
    if sid not in connected_players:
        emit("error", {"message": "Not connected to a game."})
        return

    info = connected_players[sid]
    game = server.GetGame(info["game_index"])
    if game is None:
        return

    rnd = game.GetCurrentRound()
    if rnd and not rnd.IsFinished():
        emit("error", {"message": "Round already in progress."})
        return

    rnd = game.NewRound()
    if rnd is None:
        emit("error", {"message": "Not enough players."})
        return

    rnd.DealHoleCards()
    broadcast_state(info["game_index"])
    start_turn_timer(info["game_index"])


@socketio.on("player_action")
def on_player_action(data):
    sid = request.sid
    if sid not in connected_players:
        return

    info = connected_players[sid]
    game = server.GetGame(info["game_index"])
    if game is None:
        return

    rnd = game.GetCurrentRound()
    if rnd is None or rnd.IsFinished():
        emit("error", {"message": "No active round."})
        return

    player = None
    for p in rnd.GetPlayers():
        if p.GetSid() == sid:
            player = p
            break

    if player is None:
        emit("error", {"message": "Player not in round."})
        return

    currentTurn = rnd.GetCurrentTurnPlayer()
    if currentTurn is None or currentTurn.GetID() != player.GetID():
        emit("error", {"message": "Not your turn."})
        return

    cancel_timer(info["game_index"], player.GetID())

    action = data.get("action", "")
    amount = 0
    try:
        amount = int(data.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0

    success, msg = rnd.PlayerAction(player, action, amount)
    if not success:
        emit("error", {"message": msg})
        start_turn_timer(info["game_index"])
        return

    game.AddChat(player.GetName(), msg)
    check_advance(info["game_index"])


@socketio.on("draw_cards")
def on_draw_cards(data):
    sid = request.sid
    if sid not in connected_players:
        return

    info = connected_players[sid]
    game = server.GetGame(info["game_index"])
    if game is None:
        return

    rnd = game.GetCurrentRound()
    if rnd is None or rnd.GetPhase() != "draw":
        emit("error", {"message": "Not in draw phase."})
        return

    player = None
    for p in rnd.GetPlayers():
        if p.GetSid() == sid:
            player = p
            break

    if player is None:
        return

    currentTurn = rnd.GetCurrentTurnPlayer()
    if currentTurn is None or currentTurn.GetID() != player.GetID():
        emit("error", {"message": "Not your turn to draw."})
        return

    cancel_timer(info["game_index"], player.GetID())

    indices = data.get("indices", [])
    if not isinstance(indices, list):
        indices = []

    try:
        indices = [int(i) for i in indices]
    except (ValueError, TypeError):
        indices = []

    rnd.DrawCards(player, indices)
    game.AddChat(player.GetName(), "Drew " + str(len(indices)) + " card(s).")
    check_draw_advance(info["game_index"])


@socketio.on("chat_message")
def on_chat_message(data):
    sid = request.sid
    if sid not in connected_players:
        return

    info = connected_players[sid]
    game = server.GetGame(info["game_index"])
    if game is None:
        return

    message = data.get("message", "")
    if not isinstance(message, str):
        return
    message = message.strip()
    if len(message) == 0:
        return

    game.AddChat(info["name"], message)
    socketio.emit("chat_update", {
        "name": info["name"],
        "message": message
    }, room=f"game_{info['game_index']}")


@socketio.on("set_emoji")
def on_set_emoji(data):
    sid = request.sid
    if sid not in connected_players:
        return

    info = connected_players[sid]
    game = server.GetGame(info["game_index"])
    if game is None:
        return

    emoji = data.get("emoji", "")
    if not isinstance(emoji, str):
        return

    for p in game.GetPlayers():
        if p.GetSid() == sid:
            p.SetEmoji(emoji)
            break

    broadcast_state(info["game_index"])


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)