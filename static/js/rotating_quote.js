function rotatingQuote(intervalMs) {
    return {
        quotes: [],
        quote: "",

        init() {
            const el = document.getElementById("rotating-quotes-data");
            this.quotes = el ? JSON.parse(el.textContent) : [];
            if (!this.quotes.length) return;

            let index = Math.floor(Math.random() * this.quotes.length);
            this.quote = this.quotes[index];

            setInterval(() => {
                index = (index + 1) % this.quotes.length;
                this.quote = this.quotes[index];
            }, intervalMs || 12000);
        },
    };
}
