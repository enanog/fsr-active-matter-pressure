function Rc = radio_contacto(D)
% RADIO_CONTACTO  Radius of the robot centres touching the wall [mm]: 99.5th percentile of r over the
% observed points (as comparar_ensayos.py). The wall layer is r >= Rc - D/2 (D = 33 mm).
    r = hypot(D.X, D.Y);
    Rc = percentil(r(D.OBS), 99.5);
end
