# NanoWrt

NanoWrt — experimental management/build layer поверх официальных OpenWrt и
ImmortalWrt, а не fork прошивки. Milestone 0.1 реализует только диагностику:

```sh
./nanowrt doctor
```

Запускать из каталога проекта с сохранённым `lib/`. Doctor выводит system identity,
configured effective kmods feeds и ABI, сведения об установленных пакетах,
ресурсах, LAN/default routes, connectivity/DNS, XMM и optional components.
Установки, сборки и настройки компонентов нет.

## Первичная платформа

FriendlyElec NanoPi R5S: ImmortalWrt `24.10.6`, revision `r33869-cf234f8de6d5`,
board `friendlyarm,nanopi-r5s`, target `rockchip/armv8`, architecture
`aarch64_generic`, kernel `6.6.133`, kernel package ABI
`6.6.133-1-23375d261da0c0e9da36857794905cf7`.

Milestone 0.1 прошёл SECOND hardware validation на реальном R5S / ImmortalWrt 24.10.6 /
BusyBox 1.36.1 по результатам, предоставленным пользователем: shell syntax PASS,
exit 0, 0 FAIL, 10 WARN. Подтверждены platform identity, выбор ожидаемого ABI
с исключением дополнительного modem feed, bounded IPv4 probe, XMM
`fibocom -> /dev/ttyUSB3 -> eth3` (`up=true`) и работающий Zapret.
Installed kernel metadata остаётся отдельным unverified наблюдением.
Отсутствие optional Forkop, sing-box, AmneziaWG и mwan3 не вызвало FAIL.
Намеренных runtime/config изменений при проверке не выполнялось; это не syscall-аудит.
Функциональность milestone 0.1 заморожена.

Hardware fixture — минимальная синтетическая репродукция предоставленного вывода,
не копия реальных config/status файлов. R3S проверен только fixtures;
**hardware validation R3S не проводилась**. Профили не подставляют отсутствующие
значения и не сертифицируют совместимость. Неизвестная board даёт WARN.
Пример ожидаемых строк, не результат запуска на устройстве:

```text
PASS | distribution: ImmortalWrt
PASS | release: 24.10.6
PASS | board_name: friendlyarm,nanopi-r5s
PASS | feed kernel ABI identifier: 6.6.133-1-23375d261da0c0e9da36857794905cf7
```

## Read-only design

Runtime — POSIX `/bin/sh` / BusyBox ash. Используются базовые BusyBox `cat`, `awk`,
`sort`, `dirname`. Optional `ubus`, `jsonfilter`, `uci`, `ip`, `df`, `pidof`,
`timeout`, `ping`, `nslookup`, `uname`, `busybox` проверяются перед использованием.
Bash, Python, Perl, jq, ss, pgrep и GNU coreutils на роутере не нужны.

Doctor не запускает **opkg вообще**, включая диагностические подкоманды:
их инициализация может создавать lock/temp files. Конфигурация и status database
читаются напрямую. Код не создаёт lock/temp/cache files, не пишет в `/etc`,
не выполняет init scripts, service changes, изменения маршрутов/firewall,
установку пакетов, reboot или AT-команды. Конфигурация не исполняется как shell;
`eval` не используется. Полный UCI-конфиг и пароли не печатаются.

Пробы создают ограниченный исходящий трафик: IPv4 ICMP к `1.1.1.1` и DNS запрос
`openwrt.org` через настроенный resolver, при наличии внешнего `timeout 5`.
Без timeout ICMP может использовать проверенный по help BusyBox fancy ping:
`busybox ping -c 1 -W 2 -w 3 1.1.1.1`. Числовой адрес исключает DNS lookup,
а встроенные count/wait/deadline ограничивают ожидание ответа. Без подтверждённых
`-c`, `-W`, `-w` probe пропускается. DNS без timeout остаётся WARN/skipped:
small и big nslookup используют разные resolver implementations, универсальный
native bound не предполагается. Это не пассивное наблюдение сети: возможны обычные сетевые
счётчики, DNS cache и логи принимающих служб, но конфигурация не меняется.

## Package data и identity

Все package data paths централизованы в `lib/inventory.sh`:

- `/etc/opkg.conf` — основной конфиг; override `NANOWRT_OPKG_CONF`;
- `/etc/opkg/*.conf` — дополнительные конфиги; directory override
  `NANOWRT_OPKG_CONF_DIR` (иначе учитывается `OPKG_CONF_DIR`);
- `/usr/lib/opkg/status` — база основной установки; override `NANOWRT_OPKG_STATUS`.

Overrides — абсолютные пути. `NANOWRT_ROOT` добавляет fixture prefix к путям
чтения; он **не изолирует внешние команды** и не является offline-rootfs mode.
При `OFFLINE_ROOT` или configured `option offline_root` package evidence
отбрасывается с WARN, чтобы не смешивать две установки. Автоматическое разрешение
дополнительных opkg destinations не реализовано.

Основной конфиг читается первым, затем `.conf` в порядке shell glob. Первое
объявление имени источника действует для `src` и `src/gz` совместно; дубликаты
игнорируются **до** kmods filtering. Поддерживаются стандартные поля без кавычек
и в двойных кавычках. Shell expansion и escape-интерпретации нет. Это ограниченный
read-only parser значимых для doctor директив, не полная реализация opkg.

Status database разбирается по полным records. Установленными считаются только
записи с `Status: install <flag> installed` и корректными Package/Version.
Отсутствующая, пустая, нечитаемая или malformed база даёт unknown; при повреждении
записей частичная inventory не используется. Упоминание имени в Description не
является доказательством установки.

Distribution, release, revision, target, architecture, kernel и board читаются
независимо. Противоречия release/sysinfo/kernel данным ubus и architecture
декларациям дают WARN, не перезаписывают наблюдения. ABI только извлекается из
пути effective feed, никогда не генерируется из kernel version или профиля.
Все effective kmods-like sources показаны с именами и полными URLs. Из них
ABI-capable считаются источники с распознаваемым exact identifier в пути:
`<numeric kernel>-<numeric release>-<32 hex hash>`. Другие форматы не угадываются.
Выбирается единственный уникальный ABI среди ABI-capable sources; несколько
источников с одинаковым ABI не создают ambiguity. Разные valid ABI дают WARN
без выбора. Дополнительные источники без ABI отмечаются INFO и не мешают выбору.
Имя feed и домен не используются как признак доверия.

```text
router identity == manifest identity == package metadata
```

Это invariant будущих операций, **не уже выполненная проверка doctor**. Feed ABI и версия установленного kernel package показываются отдельно.
Например, `6.6.133-1-<hash>` и `6.6.133~<hash>-r1` не сравниваются как простые
строки и не нормализуются в утверждение о совместимости. В 0.1 сравнение всегда
остаётся WARN/unverified, даже если строки совпадают. OpenWrt и
ImmortalWrt не взаимозаменяемы. Manifest resolver, package archive verification,
подписи и проверка происхождения feed не реализованы. `manifests/schema.json` —
только будущий структурный контракт. Doctor всегда предупреждает об этом.

## Статусы и ограничения detection

PASS означает конкретное наблюдение, а не разрешение устанавливать пакеты.
WARN означает unknown, конфликт evidence, optional absence или неуспешную пробу.
FAIL используется только для явно неподдерживаемой distribution.
INFO не увеличивает счётчик WARN: например, отсутствие процесса при известном
отсутствии optional package и его файлов не создаёт второе предупреждение. Нет операций apply.
Exit status: `0` без FAIL (WARN допустимы), `1` с FAIL, `2` при неверных аргументах
или относительных overrides путей.

Компоненты имеют отдельные `package: installed / absent / unknown` и
`process: running / not-running / unavailable`. `not-running` означает отсутствие
совпадающего видимого PID, не доказательство функциональной неисправности.
Отсутствие optional component, процесса или backup Ethernet не даёт platform FAIL.
AWG kernel module показан отдельно; user-space PID для kernel dataplane не нужен.

XMM определяется через `proto=xmm`. UCI selector, section identity и logical
netifd name различаются. Для named sections используется logical name; для
anonymous selector читается конфигурация, но runtime mapping остаётся unknown
с WARN. Doctor никогда не вызывает `network.interface.@interface[0]`.
Control port читается из `device`, затем `control`/`at_port`; data interface —
из ubus `l3_device`/`device`. Configured `ifname` маркируется отдельно. `up=false`
даёт WARN. Порты и data devices не привязаны к модели платы.

LAN ищется под именем `lan`; routes — только main table IPv4/IPv6, без policy
routing/failover analysis. IPv6-only default route выводится, но отдельной IPv6
connectivity probe нет. Неуспешный ICMP не доказывает отсутствие Интернета.
Нет отдельного `/overlay` mount или `MemAvailable` — WARN без догадок.

## Проверки: три разных уровня

1. **Static/design verification:** `sh -n`, ShellCheck при наличии, source guard
   явного doctor dependency graph. Guard запрещает известные mutators, opkg,
   remote installers и файловые output redirects. Это консервативная проверка
   исходников, не универсальный shell analyser и не математическое доказательство.
2. **Mocked unit tests:** реальные POSIX parsers и fixtures, isolated PATH,
   ловушки запрещённых executable calls и проверка содержимого fixture files.
   Они не доказывают отсутствие временных записей, изменений metadata или записей
   вне fixture root и не проверяют побочные эффекты настоящих utilities.
3. **Real OpenWrt validation:** второй запуск R5S подтвердил диагностику после
   исправлений ABI selection и bounded fallback: exit 0, 0 FAIL, 10 WARN.
   Результат относится к указанной R5S/ImmortalWrt платформе, не к R3S.
   Mocks не заменяют проверку настоящих ubus/uci/jsonfilter/network tools.

На компьютере с Python 3:

```sh
./tests/run.sh
NW_TEST_SHELL=/bin/dash ./tests/run.sh
# Если BusyBox установлен:
NW_TEST_SHELL='/bin/busybox ash' ./tests/run.sh
```

CI выполняет static/unit tests и fixtures в официальном Python Alpine container
с BusyBox ash/основными utilities, отключённой сетью container и read-only checkout.
Optional commands там остаются mocks. Никаких SDK, kmods builds или deployment.

Структура: `nanowrt` — dispatch; `lib/common.sh` — helpers; `inventory.sh` и
`opkg-config.awk`/`status.awk` — read-only package data; `platform.sh`, `packages.sh`,
`network.sh`, `modem.sh` — диагностика; `profiles/`, `manifests/`, `tests/` —
references, схема и проверки. Python используется только на host/CI.

## Архив на macOS и ручной запуск

На Mac, из корня проекта, создать deployment archive без AppleDouble/xattrs:

```sh
COPYFILE_DISABLE=1 tar --no-xattrs --no-acls --exclude='._*' --exclude='.DS_Store' \
  -czf /tmp/nanowrt-doctor.tar.gz nanowrt lib profiles
```

Это host-side packaging: на роутере нет macOS-specific логики. Использовать
чистый каталог распаковки, чтобы старые файлы предыдущего архива не сохранялись.
После переноса обновлённого содержимого в `/tmp/nanowrt-test`, выполнить вручную:

```sh
cd /tmp/nanowrt-test && ./nanowrt doctor
```

Exit code можно сразу посмотреть через `echo "$?"`.

Сверить семь полей identity, полный kmods URL/ABI, kernel record из status database,
XMM control/data device, LAN/routes и ресурсы с read-only источниками устройства.
Обратить внимание на WARN при недоступной сети/отключённом backup кабеле.
Для диагностики не менять конфигурацию и не перезапускать службы.

## Roadmap (не реализовано)

Проверка официальных package sources/SDK и полной identity; staging/verification;
transactional apply/rollback; собственный package feed и GitHub Actions builder;
Forkop, sing-box-extended, Mieru, kernel AWG, Fibocom/XMM integration;
Ethernet backup WAN, health/failover и LuCI. Routerich — один из возможных
upstream/reference источников. Сроки и готовность этих функций не заявлены.

Исследованные upstream источники: [BusyBox 1.36.1 ping](https://github.com/mirror/busybox/blob/1_36_1/networking/ping.c),
[BusyBox 1.36.1 nslookup](https://github.com/mirror/busybox/blob/1_36_1/networking/nslookup.c),
[стандартный opkg.conf OpenWrt 24.10](https://github.com/openwrt/openwrt/blob/openwrt-24.10/package/system/opkg/files/opkg.conf).
Стандартный файл может не содержать arch declarations; compiled-in defaults
opkg не извлекаются и не выводятся как configured architectures. Release architecture
остаётся отдельным наблюдением. Добавлена fixture конфигурации с явными arch.

## Milestone v0.2 — in development: kernel contracts slice 1

v0.1.0 remains the released baseline. Its doctor dispatch, detection, output and
exit semantics are unchanged. R5S hardware validation above applies to doctor
v0.1, not artifact compatibility; R3S remains fixture/reference tested only.

The independent `lib/kernel-identity.sh` module consumes supplied observations.
Adapter `openwrt-immortalwrt-kernel-package`, version 1, validates the supported
`VERSION~VERMAGIC-rRELEASE` family and produces `VERSION-RELEASE-VERMAGIC` only
from validated components. Unsupported formats remain UNKNOWN. Running VERSION
must match the installed package VERSION; this is limited consistency evidence,
not proof of the full active kernel build. Feed ABI is supporting evidence only.

Host schemas and router positional-argument contracts are documented in
[contracts/v1](contracts/v1/README.md). No router JSON/schema validator is claimed.
Metadata fixtures do not verify artifact bytes. No package/artifact is
installation-eligible yet; resolution eligibility is only the narrow consistency
result. There is no plan command, stage/apply, executor, download or installation.
