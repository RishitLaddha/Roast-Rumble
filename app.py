import os, json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv

from services.gemini_client import GeminiRoaster
from services.roast_engine import run_duel

# --- env ---
load_dotenv()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.getenv("FLASK_SECRET", "roast-rumble-secret-keep-it-random")

    # load presets
    with open("presets/personas.json", "r", encoding="utf-8") as f:
        personas = json.load(f)
    with open("presets/themes.json", "r", encoding="utf-8") as f:
        themes = json.load(f)

    # fun display names, don’t touch JSON
    theme_alias = {
        "wwe": "Pixel Pro Slamdome",
        "kitchen": "Heck's Kitchen",
        "arkham": "Snarkham Asylum",
    }
    for tid, t in themes.items():
        t["display_name"] = theme_alias.get(tid, t.get("name", tid))

    roaster = GeminiRoaster(model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # ---------------- ROUTES ----------------

    # Page 1: disclaimer
    @app.get("/")
    def disclaimer():
        session.clear()
        return render_template("disclaimer.html")

    # Page 2: pick players
    @app.get("/select")
    def select_players():
        return render_template("select_players.html", personas=personas)

    @app.post("/save-players")
    def save_players():
        a = request.form.get("player_a")
        b = request.form.get("player_b")
        if not a or not b or a == b or a not in personas or b not in personas:
            return redirect(url_for("select_players"))
        session["player_a"] = a
        session["player_b"] = b
        return redirect(url_for("select_arena"))

    # Page 3: pick arena
    @app.get("/arena")
    def select_arena():
        if "player_a" not in session or "player_b" not in session:
            return redirect(url_for("select_players"))
        return render_template("select_arena.html", themes=themes)

    @app.post("/save-arena")
    def save_arena():
        t = request.form.get("theme_id")
        if not t or t not in themes:
            return redirect(url_for("select_arena"))
        session["theme_id"] = t
        return redirect(url_for("fight"))

    # Page 4: fight
    @app.get("/fight")
    def fight():
        if "player_a" not in session or "player_b" not in session or "theme_id" not in session:
            return redirect(url_for("select_players"))
        a_id, b_id, t_id = session["player_a"], session["player_b"], session["theme_id"]
        return render_template(
            "fight.html",
            a=personas[a_id],
            b=personas[b_id],
            theme=themes[t_id],
            a_id=a_id,
            b_id=b_id,
            t_id=t_id,
        )

    # API: start duel
    @app.post("/api/start")
    def api_start():
        payload = request.get_json(force=True)
        a_id = payload.get("persona_a_id")
        b_id = payload.get("persona_b_id")
        t_id = payload.get("theme_id")
        rounds = int(payload.get("rounds", 3))
        style = payload.get("style", "one-liner")
        max_words = 26 if style == "one-liner" else 42

        if a_id not in personas or b_id not in personas or t_id not in themes:
            return jsonify({"error": "Bad selection"}), 400
        if a_id == b_id:
            return jsonify({"error": "Pick different bots"}), 400

        duel = run_duel(
            roaster=roaster,
            arena_theme=themes[t_id]["display_name"],
            persona_a=personas[a_id],
            persona_b=personas[b_id],
            rounds=rounds,
            max_words=max_words,
            seed=42,
        )
        session["last_duel"] = duel
        session.modified = True
        return jsonify(duel)

    # Page 5: results
    @app.get("/results")
    def results():
        duel = session.get("last_duel")
        if not duel:
            return redirect(url_for("select_players"))

        # ids selected in earlier pages (used for avatar filenames)
        a_id = session.get("player_a", "")
        b_id = session.get("player_b", "")
        t_id = session.get("theme_id", "wwe")

        a_name = duel.get("persona_a_name", "Player A")
        b_name = duel.get("persona_b_name", "Player B")

        # Build round table and scores (no draws – tie goes to the side the meter is on)
        rows = []
        a_score = 0
        b_score = 0
        for i, ev in enumerate(duel.get("events", []), 1):
            m = float(ev.get("meter_after", 0))
            if m <= 0:
                round_winner = "A"
                a_score += 1
                reason = "Meter leaned left (A landed cleaner)."
            else:
                round_winner = "B"
                b_score += 1
                reason = "Meter leaned right (B landed cleaner)."

            rows.append({
                "round": i,
                "a_line": ev.get("a_line", ""),
                "b_line": ev.get("b_line", ""),
                "meter_after": m,
                "winner": round_winner,
                "reason": reason
            })

        # Final winner label & assets
        winner_tag = "A" if a_score >= b_score else "B"
        final_winner_name = a_name if winner_tag == "A" else b_name
        final_winner_avatar = f"/static/avatars/{a_id if winner_tag=='A' else b_id}.png"

        return render_template(
            "results.html",
            arena=duel.get("arena", "Arena"),
            theme_bg=f"/static/themes/{t_id}/bg.png",
            # sides
            a_id=a_id, b_id=b_id,
            a_name=a_name, b_name=b_name,
            a_avatar=f"/static/avatars/{a_id}.png" if a_id else "/static/avatars/_placeholder.png",
            b_avatar=f"/static/avatars/{b_id}.png" if b_id else "/static/avatars/_placeholder.png",
            # score & winner
            a_score=a_score, b_score=b_score,
            final_winner_name=final_winner_name,
            final_winner_avatar=final_winner_avatar,
            # rounds
            rows=rows
        )


    return app


if __name__ == "__main__":
    app = create_app()
    # 0.0.0.0 so EC2 works, same as your Augmentarium
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
