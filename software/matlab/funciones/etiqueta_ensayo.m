function txt = etiqueta_ensayo(codigo)
% ETIQUETA_ENSAYO  '20261030_1200_22AL_60' -> '30/10 12:00 · 22AL' (date AAAAMMDD).
    p = strsplit(codigo, '_');
    d = p{1};  hm = p{2};
    txt = sprintf('%s/%s %s:%s · %s', d(7:8), d(5:6), hm(1:2), hm(3:4), p{3});
end
