function avatarCropper(initialUrl) {
    const STAGE = 240;
    const OUTPUT = 480;
    const MARGIN = 16; // pequeño margen de sobra al arrastrar, no queda pegado al borde exacto

    return {
        previewUrl: initialUrl || null,
        rawImageUrl: null,
        cropping: false,
        zoom: 1,
        offsetX: 0,
        offsetY: 0,
        naturalWidth: 0,
        naturalHeight: 0,
        dragging: false,
        dragStartX: 0,
        dragStartY: 0,
        dragStartOffsetX: 0,
        dragStartOffsetY: 0,

        onFileSelected(event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;
            if (this.rawImageUrl) URL.revokeObjectURL(this.rawImageUrl);
            this.rawImageUrl = URL.createObjectURL(file);
            this.zoom = 1;
            this.cropping = true;
        },

        onImageLoad() {
            const img = this.$refs.cropImg;
            this.naturalWidth = img.naturalWidth;
            this.naturalHeight = img.naturalHeight;
            this.centerImage();
        },

        baseScale() {
            if (!this.naturalWidth || !this.naturalHeight) return 1;
            return STAGE / Math.min(this.naturalWidth, this.naturalHeight);
        },

        displaySize() {
            const scale = this.baseScale() * this.zoom;
            return { width: this.naturalWidth * scale, height: this.naturalHeight * scale, scale };
        },

        centerImage() {
            const { width, height } = this.displaySize();
            this.offsetX = (STAGE - width) / 2;
            this.offsetY = (STAGE - height) / 2;
        },

        clampOffsets() {
            const { width, height } = this.displaySize();
            const minX = Math.min(0, STAGE - width) - MARGIN;
            const minY = Math.min(0, STAGE - height) - MARGIN;
            this.offsetX = Math.max(minX, Math.min(MARGIN, this.offsetX));
            this.offsetY = Math.max(minY, Math.min(MARGIN, this.offsetY));
        },

        onZoom() {
            this.clampOffsets();
        },

        imageStyle() {
            const { width, height } = this.displaySize();
            return `width:${width}px;height:${height}px;left:${this.offsetX}px;top:${this.offsetY}px;`;
        },

        pointerPos(event) {
            const point = event.touches && event.touches.length ? event.touches[0] : event;
            return { x: point.clientX, y: point.clientY };
        },

        startDrag(event) {
            const pos = this.pointerPos(event);
            this.dragging = true;
            this.dragStartX = pos.x;
            this.dragStartY = pos.y;
            this.dragStartOffsetX = this.offsetX;
            this.dragStartOffsetY = this.offsetY;
        },

        onDrag(event) {
            if (!this.dragging) return;
            event.preventDefault();
            const pos = this.pointerPos(event);
            this.offsetX = this.dragStartOffsetX + (pos.x - this.dragStartX);
            this.offsetY = this.dragStartOffsetY + (pos.y - this.dragStartY);
            this.clampOffsets();
        },

        endDrag() {
            this.dragging = false;
        },

        cancelCrop() {
            this.cropping = false;
            if (this.rawImageUrl) URL.revokeObjectURL(this.rawImageUrl);
            this.rawImageUrl = null;
            this.$refs.fileInput.value = "";
        },

        applyCrop() {
            const { scale } = this.displaySize();
            const canvas = this.$refs.canvas;
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, OUTPUT, OUTPUT);
            const sx = (0 - this.offsetX) / scale;
            const sy = (0 - this.offsetY) / scale;
            const sSize = STAGE / scale;
            ctx.drawImage(this.$refs.cropImg, sx, sy, sSize, sSize, 0, 0, OUTPUT, OUTPUT);
            canvas.toBlob((blob) => {
                const file = new File([blob], "avatar.jpg", { type: "image/jpeg" });
                const dt = new DataTransfer();
                dt.items.add(file);
                this.$refs.fileInput.files = dt.files;
                if (this.previewUrl && this.previewUrl.startsWith("blob:")) URL.revokeObjectURL(this.previewUrl);
                this.previewUrl = URL.createObjectURL(blob);
                this.cropping = false;
                URL.revokeObjectURL(this.rawImageUrl);
                this.rawImageUrl = null;
            }, "image/jpeg", 0.9);
        },
    };
}
