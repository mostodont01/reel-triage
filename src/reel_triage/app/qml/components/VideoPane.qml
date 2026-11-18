import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

// The reel: video with the poster until you play it, a seek bar and the
// frames Claude looked at (click one to jump there).
ColumnLayout {
	id: pane
	objectName: "videoPane"
	property string video: ""
	property string poster: ""
	property var frames: []
	spacing: 8

	onVideoChanged: player.stop()

	MediaPlayer {
		id: player
		source: pane.video
		videoOutput: output
		audioOutput: AudioOutput { volume: 0.8 }
	}

	Rectangle {
		Layout.preferredWidth: 300
		Layout.preferredHeight: 533
		radius: 8
		color: "#0d0e10"
		border.color: "#2c3038"
		clip: true

		VideoOutput {
			id: output
			anchors.fill: parent
			anchors.margins: 1
			fillMode: VideoOutput.PreserveAspectFit
			visible: player.playbackState !== MediaPlayer.StoppedState
		}
		Image {
			anchors.fill: parent
			anchors.margins: 1
			source: pane.poster
			fillMode: Image.PreserveAspectFit
			asynchronous: true
			visible: !output.visible
		}
		Text {
			anchors.centerIn: parent
			visible: !pane.video && !pane.poster
			text: "Not downloaded\n(sorted from the caption)"
			horizontalAlignment: Text.AlignHCenter
			color: "#687280"
			font.pixelSize: 12
		}
		Rectangle {  // play button
			anchors.centerIn: parent
			width: 64; height: 64; radius: 32
			color: "#c0101215"
			border.color: "#72a7ff"
			visible: pane.video !== "" && player.playbackState !== MediaPlayer.PlayingState
			Text {
				anchors.centerIn: parent
				anchors.horizontalCenterOffset: 3
				text: "▶"
				color: "#e3e7ed"
				font.pixelSize: 26
			}
		}
		MouseArea {
			anchors.fill: parent
			enabled: pane.video !== ""
			cursorShape: Qt.PointingHandCursor
			onClicked: player.playbackState === MediaPlayer.PlayingState ? player.pause() : player.play()
		}
	}

	Slider {
		Layout.preferredWidth: 300
		visible: pane.video !== ""
		from: 0
		to: Math.max(1, player.duration)
		value: player.position
		onMoved: player.position = value
	}

	Flow {
		Layout.preferredWidth: 300
		spacing: 6
		visible: pane.frames.length > 0
		Repeater {
			model: pane.frames
			delegate: Rectangle {
				required property var modelData
				width: 54; height: 96; radius: 4
				color: "#0d0e10"
				border.color: frameMouse.containsMouse ? "#72a7ff" : "#2c3038"
				clip: true
				Image {
					anchors.fill: parent
					anchors.margins: 1
					source: parent.modelData.url
					fillMode: Image.PreserveAspectCrop
					asynchronous: true
					sourceSize.width: 108
				}
				MouseArea {
					id: frameMouse
					anchors.fill: parent
					hoverEnabled: true
					cursorShape: pane.video ? Qt.PointingHandCursor : Qt.ArrowCursor
					onClicked: if (pane.video) { player.position = parent.modelData.time * 1000; player.play() }
				}
				ToolTip.visible: frameMouse.containsMouse && pane.video !== ""
				ToolTip.text: "Play from " + modelData.time.toFixed(1) + " s"
			}
		}
	}
}
