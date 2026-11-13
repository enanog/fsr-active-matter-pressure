function txt = etiqueta_ensayo(codigo)
% ETIQUETA_ENSAYO  Label of a trial in legends, panel titles and lists: its measurement code, the same
% one as the data files (R_<code>.csv, VP_<code>_robots.csv), e.g. '20261030_1200_22AL_60'.
% Text drawn with the TeX interpreter must go through texto_tex (escapes the underscores).
    txt = char(codigo);
end
