// Tragaperras de la ruleta: cada una de las 3 tiras gira por su cuenta y se
// va frenando (el intervalo entre fotogramas crece según se acerca su
// parada) hasta encajar en el cartel final — paran en momentos distintos
// (la de la izquierda antes, la de la derecha la última) para que se note
// la expectativa, como en una tragaperras de verdad. Cuando las tres han
// parado, aparece la ficha de la película.
// A los 5s de parar, el panel entero se oculta y vuelve a como estaba
// antes de girar (solo el botón "Girar la ruleta"), listo para otra
// tirada sin que la ficha anterior se quede estorbando.
const RESET_AFTER_MS = 5000;

function slotSpin(reels) {
    return {
        reels,
        indices: reels.map(() => 0),
        spinning: reels.map(() => true),
        allStopped: false,
        hidden: false,

        init() {
            this.playTick();
            const stopTimes = [1750, 2500, 3300];
            this.reels.forEach((_, r) => this.spinReel(r, stopTimes[r]));
        },

        spinReel(r, stopAt) {
            const start = performance.now();
            const tick = () => {
                const elapsed = performance.now() - start;
                const remaining = stopAt - elapsed;
                if (remaining <= 0) {
                    this.indices[r] = this.reels[r].length - 1;
                    this.spinning[r] = false;
                    this.playThunk();
                    if (this.spinning.every((s) => !s)) {
                        this.allStopped = true;
                        this.playJackpot();
                        setTimeout(() => { this.hidden = true; }, RESET_AFTER_MS);
                    }
                    return;
                }
                this.indices[r] = (this.indices[r] + 1) % this.reels[r].length;
                const delay = remaining < 350 ? 170 : remaining < 750 ? 100 : 55;
                setTimeout(tick, delay);
            };
            tick();
        },

        _ctx: null,
        _audio() {
            if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
            try {
                if (!this._ctx) this._ctx = new (window.AudioContext || window.webkitAudioContext)();
                return this._ctx;
            } catch (err) {
                return null;
            }
        },
        playTick() {
            // Tictacs discretos mientras giran, cada vez más espaciados —
            // se dispara solo, no depende de cada fotograma.
            const ctx = this._audio();
            if (!ctx) return;
            let elapsed = 0;
            const totalSpin = 3300;
            const beep = () => {
                if (elapsed >= totalSpin) return;
                const now = ctx.currentTime;
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "square";
                osc.frequency.value = 900;
                gain.gain.setValueAtTime(0.0001, now);
                gain.gain.exponentialRampToValueAtTime(0.06, now + 0.005);
                gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);
                osc.connect(gain).connect(ctx.destination);
                osc.start(now);
                osc.stop(now + 0.05);
                const step = elapsed < 1900 ? 70 : elapsed < 2700 ? 110 : 170;
                elapsed += step;
                setTimeout(beep, step);
            };
            beep();
        },
        playThunk() {
            const ctx = this._audio();
            if (!ctx) return;
            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = "triangle";
            osc.frequency.value = 140;
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.2, now + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
            osc.connect(gain).connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.2);
        },
        playJackpot() {
            const ctx = this._audio();
            if (!ctx) return;
            const now = ctx.currentTime;
            [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => {
                const t = now + i * 0.09;
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.0001, t);
                gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
                osc.connect(gain).connect(ctx.destination);
                osc.start(t);
                osc.stop(t + 0.4);
            });
        },
    };
}
