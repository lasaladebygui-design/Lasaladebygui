function introOverlay(customSoundUrl) {
    return {
        visible: true,
        _timer: null,
        customSoundUrl: customSoundUrl || "",

        init() {
            if (sessionStorage.getItem("bygui_intro_seen")) {
                this.visible = false;
                return;
            }
            this.playSound();
            this._timer = setTimeout(() => this.finish(), 5400);
        },

        skip() {
            clearTimeout(this._timer);
            this.finish();
        },

        finish() {
            this.visible = false;
            sessionStorage.setItem("bygui_intro_seen", "1");
        },

        playSound() {
            if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
                return;
            }

            // Sonido subido desde el admin (Sitio → Configuración del sitio →
            // Animación de entrada): sustituye al carrete generado por Web
            // Audio de aquí abajo. Si el navegador bloquea el autoplay sin
            // interacción previa, simplemente no suena — la animación visual
            // funciona igual.
            if (this.customSoundUrl) {
                try {
                    const audio = new Audio(this.customSoundUrl);
                    audio.volume = 0.6;
                    audio.play().catch(() => {});
                } catch (err) {
                    // Sin problema: sin sonido, la animación sigue igual.
                }
                return;
            }

            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const now = ctx.currentTime;

                // Ruido de carrete: unos "clacks" mecánicos espaciados. Si el
                // navegador bloquea el autoplay de audio (lo habitual sin
                // interacción previa del usuario), esto simplemente no suena
                // y la animación visual funciona igual.
                [0, 0.18, 0.36, 0.54, 0.72].forEach((t) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = "square";
                    osc.frequency.value = 120;
                    gain.gain.setValueAtTime(0.0001, now + t);
                    gain.gain.exponentialRampToValueAtTime(0.15, now + t + 0.01);
                    gain.gain.exponentialRampToValueAtTime(0.0001, now + t + 0.08);
                    osc.connect(gain).connect(ctx.destination);
                    osc.start(now + t);
                    osc.stop(now + t + 0.1);
                });

                const noiseBuffer = ctx.createBuffer(1, ctx.sampleRate * 1.2, ctx.sampleRate);
                const data = noiseBuffer.getChannelData(0);
                for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.05;
                const noise = ctx.createBufferSource();
                noise.buffer = noiseBuffer;
                const noiseGain = ctx.createGain();
                noiseGain.gain.setValueAtTime(0.0001, now);
                noiseGain.gain.linearRampToValueAtTime(0.04, now + 0.3);
                noiseGain.gain.linearRampToValueAtTime(0.0001, now + 1.1);
                noise.connect(noiseGain).connect(ctx.destination);
                noise.start(now);
                noise.stop(now + 1.2);
            } catch (err) {
                // Web Audio no disponible o bloqueado: sin sonido, sin problema.
            }
        },
    };
}
