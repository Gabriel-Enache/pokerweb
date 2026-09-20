const socket = io();

let gameState = null;
let myPlayerId = null;
let timerInterval = null;
let selectedDrawCards = new Set();
let joined = false;

socket.on("connect", function() {
    socket.emit("join_game", { game_index: GAME_INDEX, password: "" });
    // also request state as backup
    setTimeout(function() {
        if (!gameState) {
            socket.emit("request_state", { game_index: GAME_INDEX });
        }
    }, 1000);
});

socket.on("game_state", function(state) {
    if (!state) return;
    gameState = state;
    joined = true;

    if (state.chat) {
        var container = document.getElementById("chat-messages");
        container.innerHTML = "";
        state.chat.forEach(function(c) {
            appendChat(c.name, c.message);
        });
    }

    renderState();
});

socket.on("timer_start", function(data) {
    if (timerInterval) clearInterval(timerInterval);

    var totalTime = data.timeLimit * 1000;
    var startTime = Date.now();
    var playerId = data.playerId;

    timerInterval = setInterval(function() {
        var bar = document.getElementById("timer-bar-" + playerId);
        if (!bar) {
            clearInterval(timerInterval);
            return;
        }

        var elapsed = Date.now() - startTime;
        var remaining = Math.max(0, totalTime - elapsed);
        var pct = (remaining / totalTime) * 100;

        bar.style.width = pct + "%";

        if (pct < 20) {
            bar.className = "timer-bar danger";
        } else if (pct < 50) {
            bar.className = "timer-bar warning";
        } else {
            bar.className = "timer-bar";
        }

        if (remaining <= 0) {
            clearInterval(timerInterval);
        }
    }, 50);
});

socket.on("chat_update", function(data) {
    appendChat(data.name, data.message);
});

socket.on("error", function(data) {
    console.warn("Server error:", data.message);
});

function appendChat(name, message) {
    var container = document.getElementById("chat-messages");
    var msg = document.createElement("div");
    msg.className = "chat-msg";
    msg.innerHTML = '<span class="chat-name">' + escapeHtml(name) + ':</span> <span class="chat-text">' + escapeHtml(message) + '</span>';
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function getSeatPositions(maxPlayers) {
    var positions = [];
    var tableEl = document.querySelector(".poker-table");
    var cx = tableEl ? tableEl.offsetWidth / 2 : 350;
    var cy = tableEl ? tableEl.offsetHeight / 2 : 200;
    var rx = cx - 40;
    var ry = cy - 25;

    for (var i = 0; i < maxPlayers; i++) {
        var angle = (2 * Math.PI * i) / maxPlayers - Math.PI / 2;
        var x = cx + rx * Math.cos(angle);
        var y = cy + ry * Math.sin(angle);
        positions.push({ x: x, y: y });
    }
    return positions;
}

function cardToHTML(cardStr, selectable, index) {
    if (!cardStr || cardStr === "??") {
        return '<div class="card hidden-card"></div>';
    }

    var rank = cardStr[0];
    var suit = cardStr[1];
    var suitSymbols = { s: "\u2660", c: "\u2663", d: "\u2666", h: "\u2665" };
    var isRed = suit === "d" || suit === "h";
    var colorClass = isRed ? "red" : "black";
    var rankDisplay = rank === "T" ? "10" : rank;

    var classes = "card " + colorClass;
    var extra = "";
    if (selectable) {
        classes += " selectable";
        if (selectedDrawCards.has(index)) {
            classes += " selected";
        }
        extra = ' data-index="' + index + '" onclick="toggleDrawCard(' + index + ')"';
    }

    return '<div class="' + classes + '"' + extra + '>' + rankDisplay + (suitSymbols[suit] || suit) + '</div>';
}

function toggleDrawCard(index) {
    if (selectedDrawCards.has(index)) {
        selectedDrawCards.delete(index);
    } else {
        if (selectedDrawCards.size < 3) {
            selectedDrawCards.add(index);
        }
    }
    renderState();
}

function renderState() {
    if (!gameState) return;

    var maxP = gameState.maxPlayers;
    var players = gameState.players;
    var rnd = gameState.round;
    var positions = getSeatPositions(maxP);

    myPlayerId = null;
    for (var i = 0; i < players.length; i++) {
        if (players[i].name === PLAYER_NAME) {
            myPlayerId = players[i].id;
            break;
        }
    }

    // community cards
    var commEl = document.getElementById("community-cards");
    if (rnd && rnd.community && rnd.community.length > 0) {
        var commHTML = "";
        for (var ci = 0; ci < rnd.community.length; ci++) {
            commHTML += cardToHTML(rnd.community[ci], false, -1);
        }
        commEl.innerHTML = commHTML;
    } else {
        commEl.innerHTML = "";
    }

    // pot
    var potEl = document.getElementById("pot-display");
    potEl.textContent = rnd ? "Pot: " + rnd.pot : "Pot: 0";

    // phase
    var phaseEl = document.getElementById("phase-display");
    if (rnd) {
        var phaseNames = {
            preflop: "Pre-Flop",
            flop: "Flop",
            turn: "Turn",
            river: "River",
            showdown: "Showdown",
            draw: "Draw Phase",
            postdraw: "Post-Draw"
        };
        phaseEl.textContent = phaseNames[rnd.phase] || rnd.phase;
    } else {
        phaseEl.textContent = "Waiting for round...";
    }

    // seats
    var seatsContainer = document.getElementById("seats-container");
    seatsContainer.innerHTML = "";

    for (var si = 0; si < maxP; si++) {
        var pos = positions[si];
        var seat = document.createElement("div");
        seat.className = "player-seat";
        seat.style.left = pos.x + "px";
        seat.style.top = pos.y + "px";

        if (si < players.length) {
            var p = players[si];
            var isMyTurn = rnd && rnd.currentTurnId === p.id && !rnd.finished;
            var isFolded = p.status === "Folded";
            var isAllIn = p.status === "AllIn";

            var avatarClass = "seat-avatar";
            if (isMyTurn) avatarClass += " active-turn";
            if (isFolded) avatarClass += " folded";
            if (isAllIn) avatarClass += " allin";

            var initial = p.name.charAt(0).toUpperCase();

            var blindText = "";
            if (p.blind === "small") blindText = "SB";
            else if (p.blind === "big") blindText = "BB";

            var actionText = p.action || "";

            var cardsHTML = "";
            var isMe = p.name === PLAYER_NAME;
            var isDrawPhase = rnd && rnd.phase === "draw" && !rnd.finished;

            if (p.cards && p.cards.length > 0) {
                for (var ci2 = 0; ci2 < p.cards.length; ci2++) {
                    if (isMe && isDrawPhase) {
                        cardsHTML += cardToHTML(p.cards[ci2], true, ci2);
                    } else {
                        cardsHTML += cardToHTML(p.cards[ci2], false, -1);
                    }
                }
            }

            var handResult = "";
            if (rnd && rnd.finished && p.hand) {
                handResult = '<div class="hand-result">' + escapeHtml(p.hand.type) + '</div>';
            }

            var timerHTML = "";
            if (isMyTurn) {
                timerHTML =
                    '<div class="timer-bar-container">' +
                    '<div class="timer-bar" id="timer-bar-' + p.id + '"></div>' +
                    '</div>';
            }

            seat.innerHTML =
                '<div class="' + avatarClass + '">' +
                    initial +
                    (p.emoji ? '<span class="seat-emoji">' + p.emoji + '</span>' : '') +
                '</div>' +
                '<div class="seat-name">' + escapeHtml(p.name) + '</div>' +
                '<div class="seat-chips">$' + p.chips + '</div>' +
                (blindText ? '<div class="seat-blind">' + blindText + '</div>' : '') +
                (p.streetBet > 0 ? '<div class="seat-bet">Bet: ' + p.streetBet + '</div>' : '') +
                '<div class="seat-action">' + escapeHtml(actionText) + '</div>' +
                timerHTML +
                '<div class="seat-cards">' + cardsHTML + '</div>' +
                handResult;
        } else {
            seat.classList.add("empty-seat");
            seat.innerHTML =
                '<div class="seat-avatar">' +
                    '<span style="color:#555">+</span>' +
                '</div>' +
                '<div class="seat-name" style="color:#555">Empty</div>';
        }

        seatsContainer.appendChild(seat);
    }

    updateControls();
}

function updateControls() {
    var rnd = gameState ? gameState.round : null;
    var btnFold = document.getElementById("btn-fold");
    var btnCheck = document.getElementById("btn-check");
    var btnCall = document.getElementById("btn-call");
    var btnRaise = document.getElementById("btn-raise");
    var btnAllIn = document.getElementById("btn-allin");
    var btnStart = document.getElementById("btn-start");
    var slider = document.getElementById("raise-slider");
    var raiseInput = document.getElementById("raise-amount");
    var drawControls = document.getElementById("draw-controls");

    btnFold.disabled = true;
    btnCheck.disabled = true;
    btnCall.disabled = true;
    btnRaise.disabled = true;
    btnAllIn.disabled = true;
    slider.disabled = true;
    raiseInput.disabled = true;
    drawControls.classList.add("hidden");

    btnCall.textContent = "Call";
    btnAllIn.textContent = "All In";

    if (!rnd || rnd.finished) {
        btnStart.classList.remove("hidden");
        return;
    } else {
        btnStart.classList.add("hidden");
    }

    if (rnd.phase === "draw" && !rnd.finished) {
        if (rnd.currentTurnId === myPlayerId) {
            drawControls.classList.remove("hidden");
        }
        return;
    }

    var isMyTurn = rnd.currentTurnId === myPlayerId && !rnd.finished;
    if (!isMyTurn) return;

    var me = null;
    for (var i = 0; i < gameState.players.length; i++) {
        if (gameState.players[i].id === myPlayerId) {
            me = gameState.players[i];
            break;
        }
    }
    if (!me) return;

    var canCheck = me.streetBet >= rnd.toCall;
    var callAmount = rnd.toCall - me.streetBet;
    var minRaise = rnd.toCall - me.streetBet + 1;

    btnFold.disabled = false;

    if (canCheck) {
        btnCheck.disabled = false;
    } else {
        btnCall.disabled = false;
        btnCall.textContent = "Call " + callAmount;
    }

    if (me.chips > 0) {
        btnAllIn.disabled = false;
        btnAllIn.textContent = "All In (" + me.chips + ")";
    }

    if (me.chips > minRaise) {
        btnRaise.disabled = false;
        slider.disabled = false;
        raiseInput.disabled = false;

        slider.min = minRaise;
        slider.max = me.chips;
        slider.value = minRaise;
        raiseInput.value = minRaise;
    }
}

// ACTION BUTTONS
document.getElementById("btn-fold").addEventListener("click", function() {
    socket.emit("player_action", { action: "fold" });
});

document.getElementById("btn-check").addEventListener("click", function() {
    socket.emit("player_action", { action: "check" });
});

document.getElementById("btn-call").addEventListener("click", function() {
    socket.emit("player_action", { action: "call" });
});

document.getElementById("btn-allin").addEventListener("click", function() {
    socket.emit("player_action", { action: "allin" });
});

document.getElementById("btn-raise").addEventListener("click", function() {
    var amount = parseInt(document.getElementById("raise-amount").value);
    if (isNaN(amount) || amount <= 0) return;
    socket.emit("player_action", { action: "raise", amount: amount });
});

document.getElementById("btn-start").addEventListener("click", function() {
    socket.emit("start_round");
});

document.getElementById("btn-draw").addEventListener("click", function() {
    socket.emit("draw_cards", { indices: Array.from(selectedDrawCards) });
    selectedDrawCards.clear();
});

// CHAT
document.getElementById("chat-send").addEventListener("click", function() {
    var input = document.getElementById("chat-input");
    var msg = input.value.trim();
    if (msg.length > 0) {
        socket.emit("chat_message", { message: msg });
        input.value = "";
    }
});

document.getElementById("chat-input").addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
        document.getElementById("chat-send").click();
    }
});

// EMOJIS
document.querySelectorAll(".emoji-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
        socket.emit("set_emoji", { emoji: btn.dataset.emoji });
    });
});

// SLIDER
document.getElementById("raise-slider").addEventListener("input", function(e) {
    document.getElementById("raise-amount").value = e.target.value;
});

document.getElementById("raise-amount").addEventListener("input", function(e) {
    var slider = document.getElementById("raise-slider");
    var val = parseInt(e.target.value) || 0;
    val = Math.max(parseInt(slider.min), Math.min(parseInt(slider.max), val));
    slider.value = val;
});