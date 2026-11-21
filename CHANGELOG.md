# Changelog

## Implementováno

- Příkazová řádka: `-u`, `-p`, `-a`, `-b`, `-w`, `--insecure`, `-h`/`--help`;
  chybné argumenty končí kódem 64.
- UDP a TCP listenery na IPv4 i IPv6 (bez `-a` jeden dual-stack socket na přenos,
  s `-a` jen jedna rodina adres); socket, který nejde navázat, končí kódem 69.
- Čtení a skládání DNS zpráv: hlavička, otázka, ostatní záznamy, kontrola `OPT`.
- Zpracování zprávy, kroky 1–9 (`dropped`, `invalid` s `NOTIMP` / `FORMERR` / `REFUSED`,
  `blocked`, `forwarded`).
- Blocklisty (`-b`): načtení, kontrola formátu, porovnávání po štítcích (`NXDOMAIN` pro blokovaná jména);
  chyby při startu se vypisují jako `<soubor>:<řádek>: <zpráva>` a končí kódem 78.
- Přeposílání na DoH server (RFC 8484, `POST`) s kontrolou odpovědi, vráceným ID klienta,
  ověřením certifikátu (nebo `--insecure`) a časovým limitem `-w`, který platí pro celou výměnu.
- Souběžné zpracování: jedno vlákno na UDP datagram, jedno vlákno na TCP spojení;
  pomalý upstream ani klient nezdrží ostatní zprávy.
- Zkracování UDP odpovědí (`TC`) s limitem 512 bajtů, nebo velikostí z `OPT` (512–1232);
  odpovědi na dotazy s `OPT` nesou `OPT`.
- Log dotazů na `stdout`, jeden řádek na zprávu, ve formátu podle zadání.
- Čisté ukončení na `SIGINT` / `SIGTERM`: rozpracované dotazy dostanou `SERVFAIL` a zalogují se,
  kód ukončení 0; `SIGPIPE` a odpojení klienti program nerozbijí.
- Automatické testy (`make test`, pytest): jednotkové testy i testy celého programu.
- `Makefile` (`make`, `make NixDevShellName`, `make test`) a launcher `isa-dnsproxy`.

## Známá omezení

- Zónové soubory nejsou implementované: přepínač `-z` není podporovaný (je odmítnut jako neznámý
  s kódem 64), takže chybí lokální autoritativní odpovědi, `AA`, řetězce `CNAME` a negativní odpovědi se `SOA`.
  Vynechání zón bylo potvrzeno v issue k zadání (přijdu o body za zóny).
- Dotazy na jednom TCP spojení se zpracovávají postupně, ne mimo pořadí.
- Počet souběžných dotazů na upstream není omezen, každý dotaz otevírá nové HTTPS spojení
  a neexistuje cache.
