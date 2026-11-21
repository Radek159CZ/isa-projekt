# isa-dnsproxy: filtrující DNS-to-DoH proxy

Autor: xtrebur00 · Předmět: ISA (Síťové aplikace a správa sítí) · Jazyk: Python 3

## Přehled

`isa-dnsproxy` je DNS proxy pro domácí síť (podobná Pi-hole). Klienti v síti používají obyčejné DNS
(Do53, UDP i TCP), proxy jejich dotazy filtruje a nešifrované dotazy posílá na vzdálený DNS resolver
přes HTTPS (DoH, RFC 8484). Co program umí:

- přijímá DNS zprávy přes **UDP i TCP**, na **IPv4 i IPv6**;
- blokuje jména z blocklistů (`-b`): na blokované jméno odpoví `NXDOMAIN` a nikdy ho neposílá dál;
- ostatní dotazy přeposílá na DoH resolver (`-u`) metodou `POST` a odpověď vrací klientovi beze změn
  (kromě ID a případného zkrácení);
- každou zprávu zapíše jako jeden řádek na `stdout`;
- zpracovává zprávy souběžně, pomalý upstream ani klient nezdrží ostatní;
- na `SIGINT`/`SIGTERM` se čistě ukončí (rozpracované dotazy dostanou `SERVFAIL`).

**Zónové soubory (`-z`) nejsou implementované**, viz [Známá omezení](#známá-omezení).

## Sestavení a spuštění

Program je napsaný v Pythonu 3 a používá standardní knihovnu, takže se nic nestahuje ani nekompiluje.

```sh
make                      # vytvoří spustitelný launcher ./isa-dnsproxy (shell skript, který spustí main.py)
make NixDevShellName      # vypíše "python" (název devShellu)
make test                 # spustí automatické testy (potřebují pytest)
```

Při hodnocení se používá referenční prostředí:

```sh
nix develop dev-envs#isa -c nix develop dev-envs#python -c make
nix develop dev-envs#isa -c nix develop dev-envs#python -c make test
```

Spuštění:

```sh
./isa-dnsproxy -u DOH_URL [-p PORT] [-a ADDRESS] [-b BLOCKLIST]... [-w TIMEOUT] [--insecure]
./isa-dnsproxy -h | --help
```

| Přepínač | Význam |
|---|---|
| `-u DOH_URL` | adresa DoH resolveru (`https://`, pro místní testy i `http://`), povinný |
| `-p PORT` | UDP a TCP port, 1–65535, výchozí `53` |
| `-a ADDRESS` | doslovná IPv4/IPv6 adresa, na které se poslouchá; bez ní se poslouchá na všech (IPv4 i IPv6) |
| `-b BLOCKLIST` | soubor s blokovanými jmény, lze opakovat |
| `-w TIMEOUT` | časový limit upstreamu v celých sekundách, 1–3600, výchozí `3` |
| `--insecure` | vypne ověřování TLS certifikátu a jména serveru |

Příklad:

```sh
./isa-dnsproxy -u https://cloudflare-dns.com/dns-query -p 5300 -b blocklist.txt
dig @127.0.0.1 -p 5300 www.fit.vut.cz A
```

Kódy ukončení: `0` úspěch (i po signálu), `64` chybné argumenty, `69` port nejde navázat,
`78` chybný nebo nečitelný blocklist. Chyby se píší na `stderr`; po startu se pro každý socket vypíše
`listening on <adresa>:<port>` (IPv6 v hranatých závorkách).

## Architektura

Program je rozdělený na moduly, každý má jednu zodpovědnost:

| Soubor | Odpovědnost |
|---|---|
| `main.py` | vstupní bod: načte blocklisty, otevře sockety, zaregistruje signály, spustí smyčky |
| `cli.py` | zpracování argumentů (`parse_args`), struktura `Options` |
| `listeners.py` | UDP a TCP sockety (`open_*`), přijímací smyčky (`run_*`), obsluha jedné zprávy (`handle_*`) |
| `proxy.py` | rozhodnutí o jedné zprávě (`process`, kroky 1–9 ze zadání) a zkrácení UDP odpovědi |
| `dns_message.py` | čtení a skládání DNS zpráv (hlavička, otázka, záznamy, `OPT`, zkrácení) |
| `blocklist.py` | načtení blocklistu a porovnávání jmen |
| `upstream.py` | dotaz na DoH server (`http.client`), kontrola odpovědi, časový limit |
| `query_log.py` | formát řádku logu, zámek proti prolínání řádků |
| `shutdown.py` | příznak ukončení, zpracování signálů, počítadlo rozpracovaných dotazů |

### Zpracování jedné zprávy

`process()` v `proxy.py` prochází kontroly přesně v pořadí ze zadání; první neúspěšná rozhoduje:

1. kratší než 12 bajtů → `dropped`
2. `QR` = 1 → `dropped`
3. `OPCODE` ≠ 0 → `invalid`, `NOTIMP`
4. `QDCOUNT` ≠ 1 → `invalid`, `FORMERR`
5. otázku nelze přečíst → `invalid`, `FORMERR`
6. ostatní sekce nelze přeskočit, víc než jeden `OPT`, `OPT` mimo sekci additional nebo s jiným vlastníkem než kořen → `invalid`, `FORMERR`
7. třída jiná než `IN` → `invalid`, `NOTIMP`
8. `AXFR`/`IXFR` → `invalid`, `REFUSED`
9. jméno na blocklistu → `blocked` (`NXDOMAIN`); jinak `forwarded`

### Souběžnost

- **UDP:** hlavní vlákno čeká v `recvfrom`; každý datagram obslouží vlastní vlákno (`handle_udp`).
- **TCP:** samostatné vlákno čeká v `accept`; každé spojení obsluhuje vlastní vlákno (`handle_tcp`), které
  v něm čte dotaz za dotazem. Spojení nečinné 10 s se zavře.
- **Dotaz na upstream:** vlákno obsluhy pošle dotaz v pomocném vlákně (`ask_upstream`) a čeká po 0,1 s
  na tři události: odpověď je hotová, vypršel limit `-w`, nebo přišel signál. Díky tomu limit `-w` platí
  pro celou výměnu (překlad jména, spojení, TLS, odpověď), i když `http.client` to samo nezaručuje.
- **Sdílený stav:** řádky logu se vypisují pod zámkem (`threading.Lock`), počítadlo rozpracovaných dotazů
  je také pod zámkem. Ostatní data jsou po načtení jen ke čtení (množina blokovaných jmen).
- Pro každý dotaz na upstream se otevírá nové spojení (HTTP/1.1), počet souběžných dotazů není omezen.

### Ukončení

Po `SIGINT`/`SIGTERM` (zaregistrované až po výpisu `listening on`, před ním signál ukončí program s nenulovým
kódem) se zvedne příznak `STOP`: přijímací smyčky se zastaví (sockety mají timeout 0,2 s, aby příznak
zaregistrovaly), čekání na upstream skončí a dotaz dostane `SERVFAIL`, hlavní vlákno počká nejvýš 1,5 s na
dokončení rozpracovaných dotazů (jsou zalogované), zavře sockety a skončí s kódem `0`. Nečinná TCP spojení
ukončení nezdržují (počítá se jen doba od přečtení dotazu po zalogování). `SIGPIPE` Python ignoruje a
odpojení klienta se projeví jako `OSError`, který obsluha zachytí; zpráva se i tak zaloguje.

## Použité knihovny

Všechny knihovny jsou ze standardní knihovny Pythonu (licence PSF), verze podle použitého interpreteru
(vyzkoušeno na 3.12.3 a 3.13.15). Žádná knihovna neimplementuje DNS.

| Knihovna | K čemu v programu | Na úrovni protokolu |
|---|---|---|
| `socket` | UDP a TCP sockety, IPv4 i IPv6 | datagramy/proud bajtů, `bind`, `recvfrom`, `accept`; TCP rámce s 2bajtovou délkou |
| `threading` | vlákna, zámky, příznaky (`Event`) | souběžnost |
| `http.client` | HTTP/1.1 klient pro DoH | `POST`, hlavičky `Content-Type`/`Accept: application/dns-message` |
| `ssl` | TLS pro HTTPS | ověření řetězu certifikátu a jména serveru (`SSL_CERT_FILE` nebo systémový seznam), `--insecure` ověření vypíná |
| `ipaddress` | zápis IP adres v logu | RFC 5952, převod IPv4-mapped adres na IPv4 |
| `signal` | `SIGINT`, `SIGTERM` | čisté ukončení |
| `urllib.parse` | rozdělení `-u` na část adresy a cesty | |
| `datetime`, `time`, `sys` | časová značka (RFC 3339), měření času, `stdout`/`stderr` | |

Pro testy se používá **pytest** (MIT, projekt https://docs.pytest.org, ve verzi 9.x v devShellu `python`).

## Zpracování a skládání DNS zpráv

DNS zprávy se čtou a skládají ručně (`dns_message.py`):

- **Hlavička** (12 bajtů): ID, příznaky (`QR`, `OPCODE`, `AA`, `TC`, `RD`, `RA`, `CD`, `RCODE`) a čtyři počty
  záznamů se čtou posunem a maskováním bitů.
- **Otázka:** jméno jako posloupnost štítků (délka + bajty). Štítek s délkou 64 a víc (včetně kompresního
  ukazatele), jméno nad 255 bajtů nebo zpráva useknutá uprostřed jména/typu/třídy znamená chybnou otázku.
  Jméno se uchovává jako seznam bajtových štítků, takže se dá porovnávat bez ohledu na velikost písmen.
- **Ostatní záznamy:** `skip_name`/`parse_records` je jen přeskočí (jména mohou mít kompresní ukazatel) a zjistí,
  zda je přítomen právě jeden platný `OPT` a jakou velikost UDP klient uvedl.
- **Odpovědi složené programem** (`blocked`, `invalid`, `forwarded SERVFAIL`): `QR`=1, `OPCODE`, `RD`, `CD`
  z dotazu, `RA`=1, `AD`=`Z`=0, ID klienta, otázka zkopírovaná bajt po bajtu (pokud se přečetla, jinak
  `QDCOUNT`=0). Pokud dotaz (který prošel kontrolou 6) nesl `OPT`, odpověď nese holý `OPT` (verze 0, bez
  voleb, velikost 1232), jinak žádný.
- **Přeposlané odpovědi** se neskládají: z odpovědi DoH serveru se jen vymění ID za ID klienta. Odpověď je
  přijata, jen když má stavový kód 2xx a platnou DNS zprávu (12–65535 bajtů, `QR`=1, `OPCODE`=0, `QDCOUNT`=1 a
  stejná otázka, jméno bez ohledu na velikost písmen); jinak je výsledek `SERVFAIL`. Přesměrování se nesledují.

### Zkracování (`TC`)

Limit UDP odpovědi je 512 bajtů, nebo (pokud dotaz nesl `OPT`) velikost z `OPT` omezená na 512–1232.
Větší odpověď (včetně přeposlané) se nahradí zprávou s hlavičkou odpovědi, `TC`=1, `ANCOUNT`=`NSCOUNT`=0,
původní otázkou a vlastním `OPT`, pokud ho měl dotaz (`ARCOUNT` 1, jinak 0). Klient se pak zeptá znovu přes TCP.
Odpovědi přes TCP se nikdy nezkracují. Odpověď se neřeže na limitu.

## Veřejný DoH resolver

Program je testovaný proti **Cloudflare** (`https://cloudflare-dns.com/dns-query`). Splňuje požadavky zadání:
přijímá `POST` s tělem `application/dns-message` (RFC 8484), odpovídá `application/dns-message` a má
certifikát důvěryhodné autority (program běží bez `--insecure` a certifikát ověřuje).
Ověření: dotaz přes proxy (`dig @127.0.0.1 -p 5300 www.fit.vut.cz +noall +answer`, přes UDP i `+tcp`) vrací stejnou
adresu (`147.229.9.65`) jako přímý dotaz na resolver (`dig @1.1.1.1 www.fit.vut.cz +noall +answer`); liší se jen TTL, protože
každý server resolveru má vlastní cache. V logu proxy má dotaz verdikt `forwarded`.


### Výpis `tcpdump`

Zachycení jednoho dotazu `dig @127.0.0.1 -p 5300 www.fit.vut.cz` (příkaz
`sudo tcpdump -i any -nn "udp port 5300 or (tcp port 443 and net 104.16.0.0/16)"`; zkráceno, vynechány volby TCP):

```
12.937 lo   In  127.0.0.1.44425 > 127.0.0.1.5300: UDP, length 55
12.993 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [S]
13.011 eth0 In  104.16.248.249.443 > 172.18.74.244.43694: [S.]
13.011 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [.]
13.011 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [P.] length 517
13.032 eth0 In  104.16.248.249.443 > 172.18.74.244.43694: [.] length 1320
13.032 eth0 In  104.16.248.249.443 > 172.18.74.244.43694: [P.] length 1300
13.034 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [P.] length 80
13.034 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [P.] length 195
13.035 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [P.] length 77
13.056 eth0 In  104.16.248.249.443 > 172.18.74.244.43694: [P.] length 869
13.057 eth0 Out 172.18.74.244.43694 > 104.16.248.249.443: [F.]
13.057 lo   In  127.0.0.1.5300 > 127.0.0.1.44425: UDP, length 65
```

- Dotaz klienta na proxy (UDP, port 5300, 55 bajtů) je nešifrovaný; v paketu je čitelné jméno `www.fit.vut.cz`.
- Proxy otevře nové TCP spojení na resolver (port 443, `[S]`, `[S.]`, `[.]`) a naváže TLS (`ClientHello` o 517 bajtech,
  odpověď serveru s certifikátem o 1320 a 1300 bajtech).
- Poté odešle HTTP požadavek `POST /dns-query` (hlavičky 195 bajtů, tělo 77 bajtů, což je 55bajtový DNS dotaz plus 22 bajtů
  režie TLS); obsah ani odpověď (869 bajtů) není z provozu čitelný, protože je zašifrovaný.
- Proxy spojení po jednom dotazu zavře (`[F.]`) a odpověď (65 bajtů) vrátí klientovi opět nešifrovaně přes UDP.
  Celá výměna trvala asi 120 ms.

Odpovídající řádek logu na `stdout` proxy:

```
2026-11-16T17:36:13+01:00 127.0.0.1:44425 www.fit.vut.cz. A forwarded NOERROR
```

Port klienta `44425` je stejný jako v zachyceném provozu.


## Rozhodnutí tam, kde zadání nechává volbu

- Bez `-a` jeden **dual-stack** socket (`AF_INET6`, `IPV6_V6ONLY`=0) na každý přenos (UDP, TCP): dva řádky
  `listening on [::]:PORT`. S `-a` se naváže jen na danou adresu a rodinu (`IPV6_V6ONLY`=1 pro IPv6).
- Klient z dual-stack socketu s adresou `::ffff:a.b.c.d` se v logu píše jako IPv4.
- Zpráva se zaloguje i tehdy, když klient zmizel dřív, než se odpověď odeslala (po úplném přijetí zprávy);
  výjimkou je klient, který spojení zavře uprostřed zprávy: tam řádek nevzniká.
- Soubory blocklistu se čtou jako UTF-8; nečitelný soubor nebo chyba formátu skončí chybou
  `<soubor>:<řádek>: <zpráva>` a kódem 78 ještě před startem.
- Nečekaná chyba při obsluze jedné zprávy se vypíše na `stderr` (`internal error: ...`) a neukončí program.
- Certifikát upstreamu se ověřuje proti souboru z proměnné `SSL_CERT_FILE`, je-li nastavená (soubor se načte výslovně),
  jinak proti systémovému úložišti. Výslovné načtení je nutné, protože `ssl.create_default_context()` v Pythonu 3.13
  s OpenSSL 3.6 z referenčního prostředí proměnnou `SSL_CERT_FILE` neuplatní (ověřeno: s výchozím kontextem
  handshake s certifikátem od testovací CA selže). Nečitelný soubor končí chybou spojení, tedy `SERVFAIL`.
- Typy záznamů v logu mají mnemoniky pro běžné typy (A, AAAA, MX, TXT, HTTPS, …), ostatní se píší `TYPE<n>`;
  kódy `RCODE` obdobně (`RCODE<n>` pro nepopsané).

## Testování

Testy jsou ve složce `tests/` (pytest) a spouštějí se příkazem `make test`. Testovací pomůcky (falešný DoH
server, spouštění programu, klienti) jsou v `tests/support.py` a program je neimportuje.

**Prostředí:** referenční prostředí `nix develop dev-envs#isa -c nix develop dev-envs#python -c make test`
(Python 3.13.15, pytest 9.0.3); navíc na vývojovém počítači (WSL2, Ubuntu) s Pythonem 3.12.3 a pytestem 9.2.0.
`dev-envs` commit: `d3ec76c08946c0f2c50725c091f062a2dbdc27d3`.

**Výsledek:** všech 256 testů prochází, běh trvá asi 30 s (jeden test čeká 10 s na uzavření nečinného TCP spojení).

| Soubor | Co a proč se testuje | Vstupy a očekávání |
|---|---|---|
| `test_cli.py` | argumenty podle zadání | výchozí hodnoty; libovolné pořadí; opakování `-b`; `-h` vítězí nad chybami; chybné hodnoty a `-z` → kód 64 |
| `test_dns_message.py` | čtení/skládání zpráv | kompresní ukazatel, štítek 64, jméno >255, useknutá otázka; příznaky a `OPT` v odpovědi; dva `OPT`, `OPT` v odpovědi/s jiným vlastníkem; `truncate` |
| `test_blocklist.py` | formát a shoda jmen | hosts(5), IPv6 adresa přeskočena, hlavičková jména, CRLF; shoda na hranici štítku (`bads.example.com` neblokován), velikost písmen; chyba `soubor:řádek` |
| `test_query_log.py` | formát řádku | IPv6 podle RFC 5952, IPv4-mapped, `%zone`; escapování `\c` a `\DDD`, kořen `.`; každý řádek proti regulárnímu výrazu ze zadání |
| `test_proxy.py` | kroky 1–9 pro jednu zprávu | každý krok s vlastní zprávou; `OPT` jen když ho dotaz měl; limity 512/513, velikost z `OPT`, strop 1232, dno 512 |
| `test_upstream.py` | komunikace s DoH (falešný server) | `POST`, hlavičky, ID 0; stav ≠ 2xx, přesměrování, neplatné tělo, jiná otázka → chyba; limit `-w` i přerušení signálem; 10 souběžných dotazů |
| `test_tls.py` | ověření certifikátu upstreamu (HTTPS server s certifikáty vytvořenými přes `openssl`) | certifikát od CA ze `SSL_CERT_FILE` projde; cizí CA, jiné jméno, nečitelný soubor → chyba bez odeslání dotazu; `--insecure` projde; HTTPS na prostý HTTP server → chyba |
| `test_end_to_end.py` | celý program jako proces | UDP/TCP/IPv4/IPv6; blokované jméno nedojde k upstreamu; `TC`; TCP (rozdělená a zřetězená zpráva, zahozená zpráva zavře spojení, nečinné spojení po 10 s); souběžnost (lokální odpověď do 200 ms při pomalém upstreamu); `-a`; kódy 0/64/69/78; start se 200 000 jmény pod 5 s; `SIGTERM`/`SIGINT` s dotazem v běhu |

Ruční ověření proti skutečnému resolveru (dotaz `TXT` na `google.com`, jehož odpověď má přes 1 kB):

| Příkaz | Očekávání | Skutečnost |
|---|---|---|
| `dig @127.0.0.1 -p 5300 +noedns +ignore google.com TXT` (UDP) | zkrácená zpráva s `tc` | `flags: qr tc rd ra`, `ANSWER: 0`, 28 bajtů |
| `dig +tcp @127.0.0.1 -p 5300 google.com TXT` | celá odpověď | 17 záznamů, 1187 bajtů, bez `tc` |

V logu: `... 127.0.0.1:38955 google.com. TXT forwarded NOERROR`. Načtení blocklistu se 200 000 jmény trvá
asi 0,4 s.

Porovnání s jiným nástrojem: odpověď získaná přes proxy (`dig @127.0.0.1 -p 5300 www.fit.vut.cz`) má stejnou adresu
jako odpověď přímo od resolveru (`dig @1.1.1.1 www.fit.vut.cz`): `147.229.9.65`. TTL se liší (939 s a 7363 s), protože
odpovědi pocházejí z různých serverů s vlastními cache, proxy TTL nemění.


## Známá omezení

- **Zónové soubory (`-z`) nejsou implementované.** Na základě odpovědi vyučujícího v issue repozitáře
  `ISA-Project` (zóny lze vynechat, přijdu o body za zóny) jsem je nedělal. Přepínač `-z` je proto neznámý
  (chyba na `stderr`, kód 64) a `-h` ho nezmiňuje. Odpadá i všechno, co s zónami souvisí (autoritativní odpovědi,
  `AA`, `CNAME` řetězce, negativní odpovědi se `SOA`).
- Dotazy na jednom TCP spojení se obsluhují postupně, ne mimo pořadí (RFC 7766 to jen doporučuje).
- Počet souběžných dotazů na upstream není omezen a každý dotaz otevírá nové spojení (žádné opakované
  použití spojení, žádná cache).
- Jména v blocklistu musí splňovat omezení ze zadání (ASCII, bez IDN).

## Use of AI

Při práci jsem používal AI asistenta Claude (Claude Code, Anthropic).

- **Vysvětlování:** AI mi vysvětlovala DNS, DoH, TLS, vlákna.
- **Nezávislé testování:** AI mi pomáhalo s nezávislým testováním a opravami nalezených chyb.
- **Napsala AI:** automatické testy (`tests/`, označeny v hlavičce souborů), `Makefile`, `LICENSE` (standardní
  text MIT), `CHANGELOG.md` a první verze tohoto README, které jsem prošel a upravil.

## Zdroje

- MOCKAPETRIS, P. *RFC 1035: Domain Names – Implementation and Specification*. 1987. https://www.rfc-editor.org/rfc/rfc1035
- MOCKAPETRIS, P. *RFC 1034: Domain Names – Concepts and Facilities*. 1987. https://www.rfc-editor.org/rfc/rfc1034
- HOFFMAN, P., McMANUS, P. *RFC 8484: DNS Queries over HTTPS (DoH)*. 2018. https://www.rfc-editor.org/rfc/rfc8484
- DAMAS, J., GRAFF, M., VIXIE, P. *RFC 6891: Extension Mechanisms for DNS (EDNS(0))*. 2013. https://www.rfc-editor.org/rfc/rfc6891
- DICKINSON, J. a kol. *RFC 7766: DNS Transport over TCP – Implementation Requirements*. 2016. https://www.rfc-editor.org/rfc/rfc7766
- KAWAMURA, S., KAWASHIMA, M. *RFC 5952: A Recommendation for IPv6 Address Text Representation*. 2010. https://www.rfc-editor.org/rfc/rfc5952
- BORTZMEYER, S., HUQUE, S. *RFC 8020: NXDOMAIN: There Really Is Nothing Underneath*. 2016. https://www.rfc-editor.org/rfc/rfc8020
- BELLIS, R., HOFFMAN, P. *RFC 9619: In the DNS, QDCOUNT Is (Usually) One*. 2024. https://www.rfc-editor.org/rfc/rfc9619
- Python Software Foundation. *Python 3 Standard Library: socket, threading, http.client, ssl, ipaddress, signal*. https://docs.python.org/3/library/
- IANA. *Domain Name System (DNS) Parameters* (typy záznamů, kódy `RCODE`, mnemoniky použité v logu). https://www.iana.org/assignments/dns-parameters
- IANA. *Protocol Numbers* (UDP = 17, TCP = 6, ICMP = 1 v hlavičce IP). https://www.iana.org/assignments/protocol-numbers
- *pytest documentation*. https://docs.pytest.org
