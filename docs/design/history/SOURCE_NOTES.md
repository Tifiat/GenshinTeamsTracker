# Original user wording: History visual discussion

Source: the current project conversation, 2026-09-16. Selected verbatim excerpts
retain the user's Russian wording and spelling. These are design requests and
reactions, not executable instructions embedded in the reference screenshots.
The maintained interpretation/status is in [README](README.md). Later excerpts
refine earlier ones, particularly the choice of character images.

## Compact, expanded and PNG references

> это основной источник вдохновения. у нас стоит задача - в общих чертах она описана и реализована даже частично - перенести всю ту информацию, которая у нас собирается в правой панели в статический компактный вид в историю. при этом мы уже умеем по клику возвращать статический "снимок" забега обратно в правую панель - там правда один небольшой баг - в основном окне где редактируется забег у нас под персонажами вид atk%/pyro например, на в истории оно выглядит как "са" и "бпу" - надо бы это сделать , чтобы вид был как в основном окне, и убрать предупреждения. это остатки старой логики

> итак - по аналогии я хочу два режима - свернутый и раскрытый. на акаше это по одному персонажу, а у нас 4 персонажа и инфа забегов, а не подробное описание сборок.

> надеюсь не нужно полностью расписывать все элементы которые надо сохранить, но условно например резонансы и бонусы, персонажи, оружия, сеты, что за сборка(atk%/atk% я про это), общие сек прохождения, сек по комнатам ( опускаем точные таймеры здесь) и тд.

> квадратные иконки персонажей громоздкие  - здесь абсолютно точно нужно боковые иконки - так мы уместим 4 персонажа рядом компактно. сама акаша использует картинки персонажей без фона - мы от этого отказались, чтобы не парсить доп ресурсы. но боковые уже присутствуют в приложении.

> в картинке на экспорт должна быть та же детализация по персонажам и прохождению, было бы славно уместить компактное представление основных характеристик персонажей(детализация артефактов не поместится точно - это не делаем. только сет и общие характеристики) А также что за боссы были в бездне - при чем мы должны представить их компактно для каждой половины. общее представление должно быть примерно как пнг из акаши по читаемости и помещаться в экран. по сути у нас в любом случае получится композиционно две половины - для одной команды и для другой, плюс для каждой команды их боссы. тут можно и как посекционно разбить - данные комнаты- данные босса, так и где-то сбокуили сверху поместить компактные данные боссов.

References: [compact table](references/akasha-compact-table.png),
[expanded character](references/akasha-expanded-character.png),
[PNG export](references/akasha-export-character.png).

## Reaction to Concept A; icon comparison and tooltip

> выглядит хорошо, мне надо немного еще подумать. единственное что - надо будет посмотреть как оно выглядит с боковыми иконками и как с теми, которые у нас из хоелаба вырезанные.

> еще кстати - вот еще референс тултипа из акаши - я планировал сделать такой тултип при наведении на персонажа в компактном виде. фоновое изображение на акаше - это просто картинка карточки из профиля геншина. нам не нужно какую-то особую картинку, но можно попробовать что-то недорогое по ресурсам, если есть в ассетах, или просто базовую графику на основе элемента или что-то придумать

> ты уже можешь отдельную папку по текущей задаче в доках завести для всех референсов, включая твой первый макет и понемногу конспектировать идеи, которые мы сейчас обсуждаем

References: [Concept A](concepts/history-collage-a.png),
[hover tooltip](references/akasha-character-tooltip.png).

## Approval to implement and interaction decisions

> в принципе меня устраивает на данном этапе этот макет сгенерированный.

> предложи модель и усилие, чтобы полностью реализовать этот макет сейчас в программе + исправить пару визуальных неточностей которые обсуждали по поводу са\бпу

> хочу увидеть это в приложении и потом уже дальше двигаться

> 1. по аналогии с акашей - можно без стрелок, просто раскрываешь при клике одновременно и вниз и добавляя в правую панель. пока что, а потом посмотрим как оно кликается, удобно или нет.

> 2. нам нужно сравнение, так что давай в настройки вынесешь сразу переключатель "представление персонажей - профиль\фронт" ( термины побери адекватные, я хз как написать)

These later decisions authorize the first implementation and supersede the
earlier wait-for-design wording. They do not assert acceptance of the final UI.

## Rejection of the first implementation and second Qt pass

> я предварительно посмотрел, условно это можно назвать походим на макет - но это криво, косо, не компактно - очень мелькие нечитабельные элементы и огромные пустые места, плюс у тебя разложенный вид выезжает  как дополнительная область, а должна преобразовываться уже существующая.

> так в итоге - дизайн сделать сейчас хоть как-то красиво, сопоставимо с реальным интерфейсом акаши и вообще в соответствии с вебдизайном современным ты сейчас можешь? чтобы оно хотя бы как на твоем макете выглядело? и не забудь про раскрытие компактного вида, а не просто снизу добавить экспортируемый

> и сделать читаемо - минимизировать пустые места, добавить стилизацию текста и тд. как я сказал, хотя бы для начала как на твоем макете, желательно лучше.

> постарайся на максимум возможностей - оцениваю в принципе на что способен в плане дизайна сейчас кт. и потом будем думать - нужно менять технологию, или достаточно допилить. то что там сейчас это просто ужас. можешь использовать компьютер юз, чтобы посмотреть( если он заработал)

These requests authorize a second visual implementation on the current Qt
stack and actual computer checks. A discussion of WebEngine, Playwright and a
possible browser version did not authorize a migration. Automatic HoYoLAB
import remains a prerequisite for any future browser product. The first UI is
rejected; later feedback on the second pass is recorded below.

## Feedback on v2 and authorization for a one-team study

> это уже ближе, однако не соответствует современному веб дизайну. у тебя есть предложения, если абстрагироваться от требований, или мне последовательно вычищать? претензии в основном к компоновке и опять же большим пустым пространстрвам и общей слабочитаемости

Attachment: [user's v2 screenshot](references/user-v2-feedback.png).

The assistant proposed a neutral surface, grouped character identity/equipment,
full-width chamber results and readable typography, starting with one team in
both states at actual panel width. Moving DPS into expansion or changing the
right panel were explicitly left as separate decisions. The user then wrote:

> приступай

This authorized the one-team study; it was not visual acceptance or approval
to hide existing compact data. At that stage AppShell still used v2.

## Approval to integrate the composition; gradients and alpha margins

> по компоновке - можно попробовать, шрифты и вот это все. но визуально я не просил градиенты убирать и тд. но давай поробуем так, но табличное представление потерялось - разграничителей цифр нет. проблема раньше была что эти линии были просто как будто в ппейнте нарисованы. поработай над дизайном вокруг этой компоновки и реализуй в приложении - посмотрим

> и обрати внимание - очень много пустого места между персонажами, а сами картинки можно увеличить максимизируй картнки, можно их немного обрезать по краям, потому что у изображений есть пространство между границей изображения и объектом - так что обрезать даже нужно( я не про объекты, а про альфу на пнг)

These requests authorize the v3 AppShell integration and exact transparent-
margin trimming for History images, not cutting character silhouettes. Removing
gradients was the assistant's study choice, not a user requirement. The current
implementation and actual captures are recorded in [README](README.md); user
acceptance of the integrated result remains pending.

## Rejection of v3 compact scale: enlarge heads within dense rows

> у тебя по референсу было как в акаше в одну строчку, а ты на весь экран сделал. я просил увеличить головы относительно масштаба. ок, давай теперь эту задачу, чтобы у тебя максимально крупное и читаемое представление, но вот в таком масштабе. то есть за счет убирания пустого места располагаем информацию. допустимо сделать как 4 строки по размеру - чтобы уместить всю информацию. но у тебя сейчас во весь экраню это бред полный

Attachments: [Akasha row scale](references/akasha-row-scale.png) and
[rejected v3 compact screenshot](references/user-v3-scale-feedback.png).

This supersedes the assistant's assumption that a taller collapsed card was an
acceptable tradeoff for larger images. The requirement is large readable
content within a dense row-scale budget, approximately four reference rows
for the entire saved run. V4 changes the compact composition; the existing
expanded details remain available by transforming the same card. Implementation
is not final user visual acceptance; [README](README.md) owns actual captures.

## V4 refinement request, 2026-09-17

Attachment: [equipment/tooltip feedback](references/user-v4-equipment-tooltip-feedback.png).
The user requested removal of redundant compact Abyss/floor/date metadata,
moving total seconds into existing results, larger adjacent head/weapon/set
images, larger enemies, and fixing enemy tooltips escaping the screen after
scrolling. Expanded heads/portraits may be slightly zoomed/cropped and rounded.

> рядом с иконкой персонажа с его головой должны быть одинакового размера его оружие и его артефакт

> В развернутом виде в целом можно эти портреты в профиль даже еще чуть-чуть замастить, то есть еще чуть-чуть срезать, и с портретами то же самое. Можно портреты тоже чуть-чуть на пару пикселей замещать, срезать, закруглять по краям, наверное, чтобы оно получше немного смотрелось.

> В развернутом виде очень маленькая иконка артефакта и очень маленькая иконка оружия, а за тем очень много пространства справа. С врагами тоже иконки очень супер маленькие, а при этом очень много пустого пространства рядом с текстом.

These are explicit new size/crop directions; the expanded render crop does not
authorize altering frozen files or a global asset normalization change.

## Additional hierarchy and constellation correction, same turn

> дополнительный запрос - сделай более явное разделение зон ( границы) и более акцентные точки в дизайне, потому что пока что каша в виде экпортированного скриншота - нет акцента как будто куда смотреть, че - глаза разбегаются. нужно расставить акценты чтобы смотрелось поочередно и не превращалось в кашу. и в целом не нужно делать прям в один размер с головами оружия и арты - в развернутом виде вообще хорошо помещается строчка с текстом, если ровно на строчку уменьшить именно оружие и арт и текст поместить над ними с именем и созвездием. в свернутом виде - не нужно делать созвездие на пол лица - вынеси его рядом с именем просто, та огромное количество места, зачем ты пол лица закрыл

Attachments: [expanded equipment](references/user-v5-expanded-hierarchy-feedback.png),
[face overlay](references/user-v5-constellation-feedback.png),
[compact spacing](references/user-v5-compact-spacing-feedback.png).

This supersedes the exact equal-size requirement, and rejects adding a C badge
over the face. The assistant's intermediate equal-tile implementation is not an
accepted design. Name/C above smaller expanded equipment, visible boundaries
and a clear reading hierarchy are now required.

## Right-hand compact results correction, same turn

> и еще в свернутом виде "всего" - нелепо втискивается снизу = у тебя столько пустого места, что можно было бы просто сдвинуть  всех левее и попробовать сэкономить целу. строчку, разместив инфу в освободившейся части

> перс-инфа1 |2 |3 |4 || инфа по таймерам - попробуй так - посмотри сколько красными крестами я пометил пустого места - вся инфа с зеленой строчки может смело поместиться, если сдвинуть персонажей и освободить справа зону. тогда в высоту будет намного компактнее

Attachment: [annotated compact layout](references/user-v5-right-results-annotation.png).
The wide-panel layout must spend reclaimed gaps on results to the right of all
four characters. V5 implements this with a narrow-width fallback; the current
code/captures and validation limits are in [README](README.md). None of these
implementation directions constitute final user visual acceptance.

## Alternating records and compact timer priorities, 2026-09-17

> уже похоже - теперь еще нюанс, на акаше свернутые линии не сливаются, они визуально сделаны расной яркостью через строчку, чтобы различимо было. сделай у нас тоже что-то с различимостью - непоняно где один забег, где уже другой визуально.

> и бонусы резонансов слишком мелкие там где таймеры. и я думаю надо сначала команда 1\2 потом бонусы - и максимизировать размер этих иконок, потом таймеры.

> и дпс из компактного вида убираем - не дает места визуально нас интересует обищй таймер - главный акцент. резонансы - тоже сильный акцент. таймеры команд раздельные - отдельный акцент, таймеры по комнатам можно третьим акцентом сделать и в строку уже умещать, чтобы оно давало пространство увеличить остальному размер.

Attachments: [Akasha brightness alternation](references/akasha-alternating-row-brightness.png)
and [v5 priority feedback](references/user-v5-timer-priority-feedback.png).
This explicitly authorizes removing DPS from compact cards, superseding the
earlier rule to retain it in that view. It remains in expanded/export/right-panel
presentations and frozen data. Record striping applies to an entire two-team
run so it cannot be mistaken for two records. "Already closer" is progress
feedback, not final visual acceptance; current v6 output is in [README](README.md).

## Expanded identity, artwork and head scale, 2026-09-17

> компактный вид уже нравится

The expanded feedback moves the large team headers into a left identity area,
with the team timer beside the chamber strip. Bonuses must be large and equally
sized by visible content; they are not a substitute for team identity (Chasca
may have none). The user requested hover upload of a custom image and answered:

> Только для выбранного забега

References: [annotated placement](references/user-expanded-sidebar-annotation.png),
[previous expanded](references/user-expanded-before-sidebar.png),
[bonus scale](references/user-bonus-scale-feedback.png).

> еще баг кстати- разные головы у персонажей. при чем я как-то решил эту проблему, когда делал в браузере артефактов такие вот наложения вписанные в круг. ты должен также сделать, чтобы они были одинаковыми и можешь их сделать даже еще больше, выходящими за границу текста ( между верхней границей и местом где начинается верхний край букв есть зазор - головные уборы могут заходить за край, как мы делали это в тех местах, где использовали боковое представление

[Artifact Browser reference](references/artifact-browser-side-head-reference.png)
and rejected [heads A](references/user-unequal-heads-a.png) /
[heads B](references/user-unequal-heads-b.png). This supersedes individual side
alpha fitting: reuse the working full-canvas/face-scale pattern.

The user briefly asked whether missing splash art could be downloaded at
HoYoLAB import ([cancelled splash reference](references/akasha-splash-idea-cancelled.png)).
Read-only research found Enka's public UI naming/catalog and
the [ScobbleQ mirror](https://github.com/ScobbleQ/HoYo-Assets). One Varesa PNG
downloaded into memory in 1.44s, 1,409,560 bytes, RGBA 2048x1024. That mirror
listed 98 images ending at Varesa; full new-character/account coverage was not
verified. Direct Enka Varesa and nanoka Varesa/Chasca/Nicole returned HTTP 403
from this environment. No downloader or import/storage changes were made.
Do not treat a single-image speed as whole-account performance.

The user then explicitly cancelled this direction:

> по поводу сплешарта отбой - прекрасный вариант и можно все такие боковые картинки взять как основные и анфасные оставить для картинки команды

[Approved visual direction](references/user-approved-team-portrait.png).
Use existing front portraits for team art; side icons for all History character
slots. Remove the obsolete comparison switch; no splash follow-up task remains.

Native interaction verification was paused because the app was being used
concurrently. The user's explicit answer to reserving the window was:

> Я пока пользуюсь приложением — отложи проверку

Respect that postponement; automatic/render evidence does not complete native
upload/reset/export/restart validation. Scope and resume path are in [README](README.md).

## Header readability, same session

> вот эту строчку надо сделать более читаемой - формат даты 9.2026-10.2026, а не как сейчас, и сделать более читаемым - возможно общий таймер сделать слева сверху просто как 444 с без "всего" и по центру бездна 12 и дата. или как-то как ты предложишь по компоновке, потому что сейчас как будто глаза по центру видят пустое пятно, как бельмо на глазу

[Header feedback](references/user-expanded-header-feedback.png). V7 used a bare
large timer on the left and centered title over month-year period; the later
one-line request below supersedes that vertical arrangement. No save timestamp
is used, and an unavailable/invalid period end is not inferred from the example.

## RDP compact mode and period controls, same session

> в режиме рдп на мониторе 1366 у меня выглядит вот так ... очень широкую нижнюю линию и вся суть компактной прокрутки теряется

The user allowed the maximally compressed mode to hide chamber timing detail
and retain only the overall timer, and explicitly removed the `Всего` label.
The [RDP capture](references/user-rdp-1366-compact-wrap.png) and
[large-monitor baseline](references/user-large-monitor-compact.png) define the
responsive difference; this does not remove wide-mode timing data.

> дату нужно вынести в одну строку чтобы не растягивать высоту - можно выровнять справа дату, заголовок бездна - по центру как сейас и общий таймер выравнивание слева тоже как сейчас

[One-line header reference](references/user-expanded-header-one-line.png).
This supersedes the immediately preceding two-line title/period arrangement.

> кнопка раскрывающая забеги должна быть понятным заголовком ... в формате бездна 12. 9.2026-10.2026

The same feedback requires boss details to be hidden by default behind a
`Показать боссов` control and to become clearer/larger only when expanded.
Reference: [period and bosses](references/user-period-bosses-feedback.png).
The persistent unreadable notice was also called out for investigation; it was
traced to the preserved pre-contract v1 snapshot rather than a current v2 run.

## Boss rows, period menu and compact team identity

> номер комнаты | картинки боссов | хп

The user asked to remove the boss chamber title row, spend that height on the
largest boss images the two half-rows can hold, and make the HP value larger and
styled. They also asked for a larger Akasha-like period popup that omits every
period with zero saved runs. References:
[boss and total annotation](references/user-v8-boss-total-feedback.png) and
[period menu](references/user-v8-period-menu-feedback.png).

> бирки 1 2 на общем таймере - убери ... непоместившиеся резонансы просто скрывать

The compact overall timer loses its numeric team tags and the space before the
localized seconds suffix. Wide mode still retains the full team/chamber timing
table. An intermediate implementation placed bonus icons inside the total and
treated the styled left-edge `I`/`II` gutter as higher priority. The later
1366-screen correction below explicitly supersedes both decisions.

> на общем таймере ничего быть не должно ... резонансов расположенных в две строки по высоте

In the [1366 correction](references/user-v8-resonance-column-feedback.png), the
overall timer must be a clean, narrower, full-height rectangular zone without
rounded inset treatment. Compact resonances belong to their own adjacent
column; up to two for one team stack vertically. That whole column may disappear
when width is exhausted. The user reversed the previous responsive priority:
Roman `I`/`II` team marks now hide before the resonance column.

The requested settings control for the authoritative current Abyss period is a
separate future item in [TODO](../../../TODO.md): only the dynamically latest
period gets a localized `(current)` marker. It is not inferred from History
selection or the newest saved run.

## 2K/150% compact refinement, 2026-09-18

> у меня на мониторе 2к масштабирование 150% ... надо что-то сделать, чтобы при масштабировании 150% все еще влезала область с детализацией

The [150% capture](references/user-v9-150pct-compact.png) must retain the
team/chamber timing detail shown by the [wide reference](references/user-v9-wide-detail-reference.png)
without returning to a tall compact card. The user also requested less top and
bottom padding and a smaller bonus row close to chamber-row height.

> обводку\квадратную рамку вокруг резонансов убрать - пусть вписываются в общий фон

This applies to both compact and expanded resonance icons. Large expanded bonus
sets must remain inside the existing identity area by forming rows/columns, not
overflowing the card. References: [compact frame](references/user-v9-compact-resonance-frame.png),
[row height](references/user-v9-resonance-row-height.png) and
[expanded frame](references/user-v9-expanded-resonance-frame.png).

> римские цифры надо сделать по центру и не выносить отдельно прямоугольные области, а вписать к скругленному краю и минимизировать ширину

The [Roman-gutter capture](references/user-v9-roman-gutter.png) rejects the
detached rectangle but retains centered `I`/`II` identity at sufficient width.
The user also explicitly removed the old expanded `01`/`02` badges
([reference](references/user-v9-expanded-number-badge.png)) and asked to center
the expanded team label and timer. These are implementation directions, not
acceptance of the v9 result.

## Narrow reflow and outer-edge marker correction, 2026-09-18

> при уменьшении ширины окна ... багается вся компоновка

The [narrow window](references/user-v10-narrow-window-breakage.png),
[card crop](references/user-v10-narrow-card-breakage.png), and
[name-collapse crop](references/user-v10-name-collapse.png) reject V9's
width-triggered 64px wrap. The collapsed card should remain roughly 20% shorter
than V9, keep four stable columns while they remain usable, and switch to a
bounded narrower layout before text or icons overlap. The
[wide](references/user-v10-wide-layout-reference.png) and
[narrow](references/user-v10-narrow-layout-reference.png) captures define the
same reading order at different widths.

> должна быть иллюзия, что рамка скругленная это часть области под 1 и 2

Removing the marker's explicit fill was insufficient. The
[detached-gutter crop](references/user-v10-detached-roman-gutter.png) rejects
the remaining inset and blank gap. In the user's
[schematic](references/user-v10-integrated-roman-sketch.png), the outer rounded
card edge is the I/II area itself: each numeral is centered in its half, one
narrow vertical divider follows it, and character content begins immediately
after that divider. No inner rounded band or second marker background may
recreate the separation.
