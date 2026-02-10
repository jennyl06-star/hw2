// -------------------- ChuGL setup --------------------
GWindow.windowed(1000, 650);
GWindow.center();
GWindow.title("Mosaic Synth + ChuGL");
GWindow.mouseMode(GWindow.MOUSE_NORMAL);

GCamera cam --> GG.scene();
cam.pos(@(0, 0, 6));
cam.lookAt(@(0, 0, 0));

GLight light --> GG.scene();
light.pos(@(2, 3, 4));

GCube cube --> GG.scene();
cube.pos(@(0, 0, 0));
cube.sca(@(1, 1, 1));

GText hud --> GG.scene();
hud.size(0.18);
hud.pos(@(-2.8, 1.6, 0));
hud.maxWidth(7);
