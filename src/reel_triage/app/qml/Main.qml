import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ApplicationWindow {
	id: window
	width: 1440
	height: 900
	minimumWidth: 1000
	minimumHeight: 600
	visible: true
	title: app.current.title ? app.current.title + " — Reel Triage" : "Reel Triage"
	color: theme.background

	// Design tokens (same as VL and School Notes).
	QtObject {
		id: theme
		readonly property color background: "#17191d"
		readonly property color panel: "#202329"
		readonly property color panelRaised: "#282c33"
		readonly property color border: "#383d46"
		readonly property color text: "#e3e7ed"
		readonly property color muted: "#929ba8"
		readonly property color faint: "#687280"
		readonly property color accent: "#72a7ff"
		readonly property color ok: "#6fcf97"
		readonly property color warn: "#e5b567"
		readonly property color error: "#f28b82"
		readonly property color check: "#b69cf0"

		function verdictColor(k) {
			return k === "try" ? ok : k === "keep" ? accent : k === "maybe" ? warn
				: k === "skip" ? error : check
		}
	}

	palette.window: theme.panel
	palette.windowText: theme.text
	palette.base: theme.panelRaised
	palette.text: theme.text
	palette.button: theme.panelRaised
	palette.buttonText: theme.text
	palette.highlight: theme.accent
	palette.highlightedText: "#101722"
	palette.mid: theme.border
	palette.light: "#343943"
	palette.dark: "#15171b"
	palette.placeholderText: theme.muted

	readonly property var cur: app.current
	readonly property bool hasCurrent: cur.id !== undefined
	readonly property var pickLabels: ({ want: "Implement", tried: "Tried", dismissed: "Dismiss" })

	Connections {
		target: app
		function onMessage(text) { toast.show(text) }
		function onBusyChanged() { if (app.busy) logPanel.open = true }
	}

	Shortcut { sequence: "Ctrl+F"; onActivated: search.forceActiveFocus() }
	Shortcut { sequence: "F5"; onActivated: app.reload() }
	Shortcut { sequence: "Ctrl+I"; onActivated: if (hasCurrent) app.setPick(cur.id, "want") }

	// -- Header --------------------------------------------------------------

	header: Rectangle {
		height: 48
		color: theme.panel
		Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }

		RowLayout {
			anchors.fill: parent
			anchors.leftMargin: 14
			anchors.rightMargin: 10
			spacing: 10

			Image {
				source: Qt.resolvedUrl("../assets/reel-triage.svg")
				sourceSize.width: 24
				sourceSize.height: 24
			}
			Text {
				text: "Reel Triage"
				color: theme.muted
				font.pixelSize: 13
				font.bold: true
			}
			Text {
				Layout.leftMargin: 8
				text: app.matchCount + " of " + app.counts[""] + " reels"
				color: theme.faint
				font.pixelSize: 12
			}
			Item { Layout.fillWidth: true }
			VTextField {
				id: search
				objectName: "searchField"
				Layout.preferredWidth: 280
				placeholderText: "Search titles, captions, authors…  Ctrl+F"
				onTextChanged: searchTimer.restart()
				Timer { id: searchTimer; interval: 220; onTriggered: app.setSearch(search.text) }
			}
			Segmented {
				options: [{ key: "best", label: "Best first" }, { key: "new", label: "Newest" }]
				value: app.sortMode
				onPicked: key => app.setSortMode(key)
			}
			Spinner { visible: app.busy; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
			VButton {
				text: logPanel.open ? "Hide log" : "Log"
				subtle: true
				visible: app.log !== ""
				onClicked: logPanel.open = !logPanel.open
			}
			VButton {
				objectName: "getNewButton"
				text: "Get new reels…"
				onClicked: getNew.open()
			}
			VButton {
				objectName: "runButton"
				kind: app.busy ? "danger" : "primary"
				text: app.busy ? "Stop" : app.pending > 0 ? "Sort & review (" + app.pending + ")" : "Sort & review"
				enabled: app.busy || app.pending > 0
				onClicked: app.busy ? app.stopPipeline() : app.runPipeline()
				ToolTip.visible: hovered && !app.busy
				ToolTip.delay: 400
				ToolTip.text: "Sorts new reels from their captions, then downloads and fully reviews the promising ones.\nStops by itself at 80 % of the 5-hour window."
			}
		}
	}

	// -- Body ------------------------------------------------------------------

	ColumnLayout {
		anchors.fill: parent
		spacing: 0

		RowLayout {
			Layout.fillWidth: true
			Layout.fillHeight: true
			spacing: 0

			// Sidebar: filters + usage
			Rectangle {
				Layout.preferredWidth: 236
				Layout.fillHeight: true
				color: theme.panel
				Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }

				ColumnLayout {
					anchors.fill: parent
					anchors.rightMargin: 1
					spacing: 0

					Flickable {
						Layout.fillWidth: true
						Layout.fillHeight: true
						contentHeight: filters.implicitHeight + 20
						clip: true
						boundsBehavior: Flickable.StopAtBounds
						ScrollBar.vertical: ScrollBar {}

						ColumnLayout {
							id: filters
							width: parent.width
							y: 10
							spacing: 1

							SectionTitle { text: "VERDICT" }
							Repeater {
								model: app.verdictFilters
								delegate: SideItem {
									required property var modelData
									label: modelData.label
									count: app.counts[modelData.key] || 0
									dot: modelData.key ? theme.verdictColor(modelData.key) : "transparent"
									selected: app.verdictFilter === modelData.key
									onClicked: app.setVerdictFilter(modelData.key)
								}
							}

							SectionTitle { text: "YOUR PICKS" }
							Repeater {
								model: app.pickFilters
								delegate: SideItem {
									required property var modelData
									label: modelData.label
									count: app.counts["pick:" + modelData.key] || 0
									selected: app.pickFilter === modelData.key
									onClicked: app.setPickFilter(modelData.key)
								}
							}

							SectionTitle { text: "CATEGORY" }
							SideItem {
								label: "All categories"
								count: app.counts[""] || 0
								selected: app.categoryFilter === ""
								onClicked: app.setCategoryFilter(app.categoryFilter)
							}
							Repeater {
								model: app.categories
								delegate: SideItem {
									required property var modelData
									label: modelData.name
									count: modelData.count
									selected: app.categoryFilter === modelData.name
									onClicked: app.setCategoryFilter(modelData.name)
								}
							}
						}
					}

					UsagePanel {
						Layout.fillWidth: true
						usage: app.usage
					}
				}
			}

			// The list
			Rectangle {
				Layout.preferredWidth: 420
				Layout.fillHeight: true
				color: theme.background
				Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }

				ListView {
					id: list
					objectName: "reelList"
					anchors.fill: parent
					anchors.rightMargin: 1
					model: app.reels
					clip: true
					focus: true
					keyNavigationEnabled: true
					highlightMoveDuration: 0
					currentIndex: -1
					boundsBehavior: Flickable.StopAtBounds
					ScrollBar.vertical: ScrollBar {}
					onCurrentIndexChanged: if (currentIndex !== app.currentRow) app.selectRow(currentIndex)
					Connections {
						target: app
						function onFiltersChanged() { list.currentIndex = app.currentRow }
						function onCurrentChanged() { if (list.currentIndex !== app.currentRow) list.currentIndex = app.currentRow }
					}
					Keys.onPressed: event => {
						if (!window.hasCurrent) return
						const keys = { "i": "want", "t": "tried", "d": "dismissed" }
						if (keys[event.text]) { app.setPick(window.cur.id, keys[event.text]); event.accepted = true }
					}

					delegate: ReelRow {}

					Text {
						anchors.centerIn: parent
						visible: list.count === 0
						text: app.counts[""] ? "Nothing matches these filters." : "No reels yet: Get new reels…"
						color: theme.muted
						font.pixelSize: 13
					}
				}
			}

			// The selected reel
			Rectangle {
				Layout.fillWidth: true
				Layout.fillHeight: true
				color: theme.background

				Text {
					anchors.centerIn: parent
					visible: !window.hasCurrent
					text: "Pick a reel on the left.\n\n↑ ↓ to move · I implement · T tried · D dismiss"
					horizontalAlignment: Text.AlignHCenter
					color: theme.faint
					font.pixelSize: 13
				}

				Flickable {
					id: detail
					objectName: "detail"
					anchors.fill: parent
					visible: window.hasCurrent
					contentHeight: detailRow.implicitHeight + 48
					clip: true
					boundsBehavior: Flickable.StopAtBounds
					ScrollBar.vertical: ScrollBar {}
					Connections { target: app; function onCurrentChanged() { detail.contentY = 0 } }

					RowLayout {
						id: detailRow
						x: 24
						y: 24
						width: detail.width - 48
						spacing: 24

						VideoPane {
							Layout.alignment: Qt.AlignTop
							visible: window.cur.video || window.cur.poster || (window.cur.frames || []).length
							video: window.cur.video || ""
							poster: window.cur.poster || ""
							frames: window.cur.frames || []
						}

						ColumnLayout {
							Layout.alignment: Qt.AlignTop
							Layout.fillWidth: true
							Layout.maximumWidth: 720
							spacing: 12

							Flow {
								Layout.fillWidth: true
								spacing: 6
								Badge {
									text: window.cur.verdictLabel || ""
									tint: theme.verdictColor(window.cur.verdict)
									dashed: !window.cur.reviewed
								}
								Chip { text: window.cur.category || ""; visible: text !== "" }
								Text {
									visible: window.cur.quality > 0
									text: "★".repeat(window.cur.quality || 0) + "☆".repeat(5 - (window.cur.quality || 0))
									color: theme.warn
									font.pixelSize: 13
									height: 22
									verticalAlignment: Text.AlignVCenter
								}
								Repeater {
									model: window.cur.collections || []
									delegate: Chip { required property var modelData; text: "▣ " + modelData; tint: theme.accent }
								}
							}

							Text {
								objectName: "detailTitle"
								Layout.fillWidth: true
								text: window.cur.title || ""
								color: theme.text
								font.pixelSize: 20
								font.bold: true
								wrapMode: Text.Wrap
							}

							Body { text: window.cur.comment || ""; color: theme.text; font.pixelSize: 14 }
							Body { text: window.cur.note || ""; color: theme.muted; font.italic: true }

							// The tool, checked on the web
							Rectangle {
								Layout.fillWidth: true
								visible: (window.cur.tool || {}).name ? true : false
								implicitHeight: toolCol.implicitHeight + 20
								radius: 6
								color: theme.panel
								border.color: theme.border
								ColumnLayout {
									id: toolCol
									x: 12; y: 10
									width: parent.width - 24
									spacing: 6
									readonly property var t: window.cur.tool || {}
									Text { text: toolCol.t.name || ""; color: theme.text; font.bold: true; font.pixelSize: 13 }
									LinkText { url: toolCol.t.url || "" }
									Flow {
										Layout.fillWidth: true
										spacing: 6
										Chip { visible: toolCol.t.stars !== ""; text: "★ " + toolCol.t.stars }
										Chip { visible: toolCol.t.lastUpdate !== ""; text: "updated " + toolCol.t.lastUpdate }
										Chip { visible: !!toolCol.t.alreadyHave; text: "you have it"; tint: theme.ok }
										Chip { visible: !!toolCol.t.builtIn; text: "built in"; tint: theme.ok }
									}
									Body { visible: text !== ""; text: toolCol.t.safety ? "⚠ " + toolCol.t.safety : ""; color: theme.warn }
								}
							}

							// What to do / install
							RowLayout {
								Layout.fillWidth: true
								visible: (window.cur.action || "") !== ""
								spacing: 8
								Rectangle {
									Layout.fillWidth: true
									implicitHeight: actionText.implicitHeight + 16
									radius: 5
									color: "#15171b"
									border.color: theme.border
									TextEdit {
										id: actionText
										x: 10; y: 8
										width: parent.width - 20
										text: window.cur.action || ""
										readOnly: true
										selectByMouse: true
										wrapMode: TextEdit.Wrap
										color: theme.text
										font.family: "monospace"
										font.pixelSize: 12
									}
								}
								VButton { text: "Copy"; onClicked: app.copy(window.cur.action) }
							}

							Flow {
								Layout.fillWidth: true
								spacing: 6
								visible: (window.cur.projects || []).length > 0
								Repeater {
									model: window.cur.projects || []
									delegate: Chip { required property var modelData; text: modelData; tint: theme.ok }
								}
							}

							Fold { title: "What the reel says"; content: window.cur.summary || "" }
							Fold { title: "Caption"; content: window.cur.caption || ""; mono: true }

							ColumnLayout {
								Layout.fillWidth: true
								visible: (window.cur.links || []).length > 0
								spacing: 3
								Text { text: "Links"; color: theme.muted; font.pixelSize: 12; font.bold: true }
								Repeater {
									model: window.cur.links || []
									delegate: LinkText { required property var modelData; url: modelData }
								}
							}

							RowLayout {
								Layout.fillWidth: true
								Layout.topMargin: 4
								spacing: 8
								Text {
									text: [window.cur.author, window.cur.posted].filter(x => x).join(" · ")
									color: theme.muted
									font.pixelSize: 12
								}
								VButton {
									text: "Open on Instagram ↗"
									subtle: true
									onClicked: Qt.openUrlExternally(window.cur.url)
								}
								Item { Layout.fillWidth: true }
							}

							Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

							RowLayout {
								spacing: 8
								Repeater {
									model: ["want", "tried", "dismissed"]
									delegate: VButton {
										required property string modelData
										objectName: "pick_" + modelData
										readonly property bool on: window.cur.pick === modelData
										text: (on ? "✓ " : "") + window.pickLabels[modelData]
										kind: on && modelData === "want" ? "primary" : "normal"
										onClicked: app.setPick(window.cur.id, modelData)
									}
								}
								Text {
									Layout.leftMargin: 6
									visible: window.cur.pick === "want"
									text: "Say /reels in Claude Code to install it"
									color: theme.muted
									font.pixelSize: 11
								}
							}
						}
					}
				}
			}
		}

		// Pipeline log
		Rectangle {
			id: logPanel
			property bool open: false
			Layout.fillWidth: true
			Layout.preferredHeight: open ? 200 : 0
			visible: open
			color: "#121417"
			Rectangle { width: parent.width; height: 1; color: theme.border }

			ScrollView {
				id: logScroll
				anchors.fill: parent
				anchors.margins: 8
				anchors.topMargin: 9
				TextArea {
					id: logText
					objectName: "logText"
					text: app.log
					readOnly: true
					selectByMouse: true
					wrapMode: TextEdit.NoWrap
					color: "#c9ced6"
					font.family: "monospace"
					font.pixelSize: 11
					background: null
					onTextChanged: cursorPosition = length
				}
			}
		}
	}

	// -- Get new reels ---------------------------------------------------------

	Popup {
		id: getNew
		objectName: "getNewPopup"
		modal: true
		anchors.centerIn: parent
		width: 560
		padding: 18
		onOpened: { result.text = ""; links.forceActiveFocus() }
		background: Rectangle { radius: 8; color: theme.panel; border.color: theme.border }

		ColumnLayout {
			anchors.fill: parent
			spacing: 10

			Text { text: "Get new reels"; color: theme.text; font.pixelSize: 16; font.bold: true }
			Body {
				color: theme.muted
				text: "Paste Instagram links (Share → Copy link), or import a data export zip "
					+ "(Instagram → Your activity → Download your information → Saved, JSON). "
					+ "Reels you already have are skipped. Then press Sort & review."
			}
			Rectangle {
				Layout.fillWidth: true
				Layout.preferredHeight: 110
				radius: 5
				color: "#15171b"
				border.color: links.activeFocus ? theme.accent : theme.border
				ScrollView {
					anchors.fill: parent
					anchors.margins: 2
					TextArea {
						id: links
						objectName: "linksField"
						placeholderText: "https://www.instagram.com/reel/…"
						color: theme.text
						font.pixelSize: 12
						wrapMode: TextEdit.WrapAnywhere
						background: null
					}
				}
			}
			RowLayout {
				Layout.fillWidth: true
				spacing: 8
				VButton {
					text: "Add links"
					kind: "primary"
					enabled: links.text.trim() !== ""
					onClicked: { result.text = app.addLinks(links.text); links.text = "" }
				}
				VButton { text: "Import export zip…"; onClicked: zipDialog.open() }
				Item { Layout.fillWidth: true }
				VButton { text: "Close"; subtle: true; onClicked: getNew.close() }
			}
			Body { id: result; color: theme.ok; visible: text !== "" }
			Body {
				color: theme.faint
				font.pixelSize: 11
				text: "Or say /reels in Claude Code: it reads your newest saves on Instagram for you."
			}
		}
	}

	FileDialog {
		id: zipDialog
		title: "Instagram data export"
		nameFilters: ["Instagram export (*.zip *.json *.html)", "All files (*)"]
		onAccepted: result.text = app.importExport(selectedFile.toString())
	}

	Toast {
		id: toast
		anchors.horizontalCenter: parent.horizontalCenter
		anchors.bottom: parent.bottom
		anchors.bottomMargin: 18
		z: 10
	}

	// -- Small components ------------------------------------------------------

	component ReelRow: Rectangle {
		id: row
		required property int index
		required property string reelId
		required property string title
		required property string verdict
		required property string verdictLabel
		required property string category
		required property int quality
		required property string author
		required property string thumb
		required property string pick
		required property bool reviewed
		required property string saved
		readonly property bool current: ListView.isCurrentItem

		width: ListView.view.width
		height: 84
		color: current ? "#243049" : rowMouse.containsMouse ? "#1e2127" : "transparent"
		opacity: pick === "dismissed" || pick === "tried" ? 0.55 : 1
		Rectangle { anchors.bottom: parent.bottom; x: 12; width: parent.width - 24; height: 1; color: "#23262c" }
		Rectangle { visible: row.current; width: 3; height: parent.height; color: theme.accent }

		RowLayout {
			anchors.fill: parent
			anchors.leftMargin: 12
			anchors.rightMargin: 12
			spacing: 10

			Rectangle {
				Layout.preferredWidth: 40
				Layout.preferredHeight: 70
				radius: 4
				color: "#23262c"
				clip: true
				Image {
					anchors.fill: parent
					source: row.thumb
					sourceSize.width: 80
					fillMode: Image.PreserveAspectCrop
					asynchronous: true
				}
				Text {
					anchors.centerIn: parent
					visible: !row.thumb
					text: row.category ? row.category[0].toUpperCase() : "?"
					color: theme.faint
					font.pixelSize: 15
					font.bold: true
				}
			}

			ColumnLayout {
				Layout.fillWidth: true
				spacing: 4
				Text {
					Layout.fillWidth: true
					text: row.title
					color: theme.text
					font.pixelSize: 13
					font.bold: row.reviewed
					elide: Text.ElideRight
					maximumLineCount: 2
					wrapMode: Text.Wrap
				}
				RowLayout {
					spacing: 6
					Badge { text: row.verdictLabel; tint: theme.verdictColor(row.verdict); dashed: !row.reviewed; small: true }
					Text {
						visible: row.quality > 0
						text: "★".repeat(row.quality)
						color: theme.warn
						font.pixelSize: 11
					}
					Text { text: row.category; color: theme.muted; font.pixelSize: 11 }
					Text {
						visible: row.pick !== ""
						text: row.pick === "want" ? "● implement" : row.pick === "tried" ? "✓ tried" : "✕ dismissed"
						color: row.pick === "want" ? theme.accent : theme.faint
						font.pixelSize: 11
						font.bold: row.pick === "want"
					}
				}
				Text {
					Layout.fillWidth: true
					text: [row.author, row.saved].filter(x => x).join(" · ")
					color: theme.faint
					font.pixelSize: 11
					elide: Text.ElideRight
				}
			}
		}
		MouseArea {
			id: rowMouse
			anchors.fill: parent
			hoverEnabled: true
			onClicked: { row.ListView.view.currentIndex = row.index; row.ListView.view.forceActiveFocus() }
		}
	}

	component SectionTitle: Text {
		Layout.leftMargin: 14
		Layout.topMargin: 12
		Layout.bottomMargin: 4
		color: theme.muted
		font.pixelSize: 10
		font.bold: true
		font.letterSpacing: 1.2
	}

	component SideItem: Rectangle {
		id: item
		property string label
		property int count
		property color dot: "transparent"
		property bool selected: false
		signal clicked()
		Layout.fillWidth: true
		Layout.leftMargin: 6
		Layout.rightMargin: 6
		implicitHeight: 28
		radius: 5
		color: selected ? "#243049" : itemMouse.containsMouse ? theme.panelRaised : "transparent"
		RowLayout {
			anchors.fill: parent
			anchors.leftMargin: 10
			anchors.rightMargin: 10
			spacing: 8
			Rectangle { visible: item.dot !== Qt.color("transparent"); width: 8; height: 8; radius: 4; color: item.dot }
			Text {
				Layout.fillWidth: true
				text: item.label
				color: item.selected ? theme.text : "#c9ced6"
				font.pixelSize: 12
				font.bold: item.selected
				elide: Text.ElideRight
			}
			Text { text: item.count; color: theme.faint; font.pixelSize: 11 }
		}
		MouseArea { id: itemMouse; anchors.fill: parent; hoverEnabled: true; onClicked: item.clicked() }
	}

	component Badge: Rectangle {
		id: badge
		property alias text: badgeText.text
		property color tint: theme.accent
		property bool dashed: false
		property bool small: false
		implicitWidth: badgeText.implicitWidth + (small ? 12 : 16)
		implicitHeight: small ? 18 : 22
		radius: 4
		color: dashed ? "transparent" : Qt.rgba(tint.r, tint.g, tint.b, 0.16)
		border.color: Qt.rgba(tint.r, tint.g, tint.b, dashed ? 0.55 : 0.4)
		Text {
			id: badgeText
			anchors.centerIn: parent
			color: badge.tint
			font.pixelSize: badge.small ? 10 : 11
			font.bold: true
			font.italic: badge.dashed
		}
	}

	component Chip: Rectangle {
		id: chip
		property alias text: chipText.text
		property color tint: theme.muted
		implicitWidth: chipText.implicitWidth + 14
		implicitHeight: 22
		radius: 11
		color: Qt.rgba(tint.r, tint.g, tint.b, 0.10)
		border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.30)
		Text { id: chipText; anchors.centerIn: parent; color: Qt.lighter(chip.tint, 1.15); font.pixelSize: 11 }
	}

	component Body: Text {
		Layout.fillWidth: true
		visible: text !== ""
		wrapMode: Text.Wrap
		color: theme.text
		font.pixelSize: 13
		lineHeight: 1.15
		textFormat: Text.PlainText
	}

	component LinkText: Text {
		property string url
		Layout.fillWidth: true
		visible: url !== ""
		text: url
		color: theme.accent
		font.pixelSize: 12
		elide: Text.ElideMiddle
		MouseArea {
			anchors.fill: parent
			cursorShape: Qt.PointingHandCursor
			onClicked: Qt.openUrlExternally(parent.url)
		}
	}

	component Fold: ColumnLayout {
		id: fold
		property string title
		property string content
		property bool mono: false
		property bool expanded: false
		Layout.fillWidth: true
		visible: content !== ""
		spacing: 6
		Text {
			text: (fold.expanded ? "▾ " : "▸ ") + fold.title
			color: theme.muted
			font.pixelSize: 12
			font.bold: true
			MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: fold.expanded = !fold.expanded }
		}
		TextEdit {
			Layout.fillWidth: true
			visible: fold.expanded
			text: fold.content
			readOnly: true
			selectByMouse: true
			wrapMode: TextEdit.Wrap
			color: "#c9ced6"
			font.pixelSize: 12
			font.family: fold.mono ? "monospace" : ""
		}
	}

	component Segmented: Row {
		id: seg
		property var options: []
		property string value
		signal picked(string key)
		spacing: 0
		Repeater {
			model: seg.options
			delegate: Rectangle {
				id: opt
				required property var modelData
				required property int index
				readonly property bool on: seg.value === modelData.key
				width: optText.implicitWidth + 20
				height: 28
				radius: 5
				color: on ? "#2f3e5c" : optMouse.containsMouse ? theme.panelRaised : "#1d2025"
				border.color: on ? "#4a6ea8" : "#3a404a"
				Text { id: optText; anchors.centerIn: parent; text: opt.modelData.label; color: opt.on ? theme.text : theme.muted; font.pixelSize: 12 }
				MouseArea { id: optMouse; anchors.fill: parent; hoverEnabled: true; onClicked: seg.picked(opt.modelData.key) }
			}
		}
	}

	component Spinner: Item {
		id: spinner
		Rectangle { anchors.fill: parent; radius: width / 2; color: "transparent"; border.width: 2; border.color: "#3a404a" }
		Rectangle { width: 4; height: 4; radius: 2; color: theme.accent; x: spinner.width / 2 - 2; y: 0 }
		RotationAnimator on rotation { from: 0; to: 360; duration: 900; loops: Animation.Infinite; running: spinner.visible }
	}
}
