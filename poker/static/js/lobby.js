var socket = io();

var pendingJoinIndex = null;
var pendingJoinPassword = "";

socket.on("connect", function() {
    socket.emit("get_lobbies");
});

socket.on("lobby_list", function(games) {
    var list = document.getElementById("games-list");
    if (games.length === 0) {
        list.innerHTML = '<p class="no-games">No games available. Create one!</p>';
        return;
    }

    list.innerHTML = "";
    games.forEach(function(g) {
        var card = document.createElement("div");
        card.className = "game-card";

        var variantNames = {
            TexasHoldEm: "Texas Hold'Em",
            Omaha: "Omaha",
            FiveCardDraw: "Five Card Draw"
        };

        card.innerHTML =
            '<div class="game-info">' +
                '<span class="game-variant">' + (variantNames[g.variant] || g.variant) + '</span>' +
                '<span>Buy In: ' + g.buyin + '</span>' +
                '<span>Blinds: ' + g.smallBlind + '/' + g.bigBlind + '</span>' +
                '<span>Players: ' + g.players + '/' + g.maxPlayers + '</span>' +
                '<span>Time: ' + g.timeControl + 's</span>' +
                (g.hasPassword ? '<span>\uD83D\uDD12</span>' : '') +
            '</div>' +
            '<button class="game-join-btn" data-index="' + g.index + '" data-has-password="' + g.hasPassword + '">' +
                'Join' +
            '</button>';
        list.appendChild(card);
    });

    document.querySelectorAll(".game-join-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var index = parseInt(btn.dataset.index);
            var hasPass = btn.dataset.hasPassword === "true";
            if (hasPass) {
                pendingJoinIndex = index;
                document.getElementById("password-modal").classList.remove("hidden");
                document.getElementById("modal-password").value = "";
                document.getElementById("modal-password").focus();
            } else {
                joinGame(index, "");
            }
        });
    });
});

document.getElementById("modal-join").addEventListener("click", function() {
    var pw = document.getElementById("modal-password").value;
    document.getElementById("password-modal").classList.add("hidden");
    if (pendingJoinIndex !== null) {
        joinGame(pendingJoinIndex, pw);
        pendingJoinIndex = null;
    }
});

document.getElementById("modal-cancel").addEventListener("click", function() {
    document.getElementById("password-modal").classList.add("hidden");
    document.getElementById("modal-password").value = "";
    pendingJoinIndex = null;
});

document.getElementById("modal-password").addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
        document.getElementById("modal-join").click();
    }
});

function joinGame(index, password) {
    pendingJoinPassword = password;

    // remove old listeners to avoid stacking
    socket.off("game_state");
    socket.off("error");

    socket.on("game_state", function onJoinState() {
        socket.off("game_state", onJoinState);
        socket.off("error", onJoinError);
        window.location.href = "/table/" + index;
    });

    var onJoinError = function(data) {
        socket.off("game_state");
        socket.off("error", onJoinError);
        alert(data.message);
        // re-register lobby list listener
        socket.emit("get_lobbies");
    };
    socket.on("error", onJoinError);

    socket.emit("join_game", { game_index: index, password: password });
}

document.getElementById("create-btn").addEventListener("click", function() {
    var data = {
        variant: document.getElementById("create-variant").value,
        buyin: document.getElementById("create-buyin").value,
        smallBlind: document.getElementById("create-sb").value,
        bigBlind: document.getElementById("create-bb").value,
        maxPlayers: document.getElementById("create-max").value,
        timeControl: document.getElementById("create-time").value,
        password: document.getElementById("create-password").value
    };

    socket.off("game_created");
    socket.off("error");

    socket.on("game_created", function onCreated(result) {
        socket.off("game_created", onCreated);
        socket.off("error", onCreateError);
        joinGame(result.game_index, data.password);
    });

    var onCreateError = function(errData) {
        socket.off("game_created");
        socket.off("error", onCreateError);
        alert(errData.message);
    };
    socket.on("error", onCreateError);

    socket.emit("create_game", data);
});