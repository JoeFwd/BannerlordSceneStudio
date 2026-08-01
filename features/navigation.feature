Feature: Camera navigation
  The map view is driven from the keyboard by physical key position (event.code),
  so it works on QWERTY (WASD) and AZERTY (ZQSD) alike, plus the arrow keys.
  Panning is guarded against typing, and its speed eases with zoom but is floored.

  Background:
    Given the studio is loaded with the campaign scene

  Scenario: WASD keys pan the camera
    When I hold the "w" key for 500 ms
    Then the camera target moves
    When I hold the "d" key for 500 ms
    Then the camera target moves

  Scenario: ZQSD keys pan the camera on an AZERTY layout
    When I hold the AZERTY physical "KeyW" key for 500 ms
    Then the camera target moves
    When I hold the AZERTY physical "KeyA" key for 500 ms
    Then the camera target moves

  Scenario: Arrow keys pan the camera
    When I hold the "ArrowUp" key for 500 ms
    Then the camera target moves
    When I hold the "ArrowLeft" key for 500 ms
    Then the camera target moves

  Scenario: Typing in a text field does not pan the camera
    When I focus the town-radius input and type "wasd"
    Then the field contains "wasd"
    And the camera target does not move

  Scenario: Pan speed eases with zoom but is floored, not zoom-independent
    When I record the pan for an 800 ms hold fully zoomed out
    And I record the pan for an 800 ms hold after zooming in 5 notches
    And I record the pan for an 800 ms hold after zooming in 25 more notches
    Then the pan distance shrinks as the zoom deepens
    And the deep-zoom pan is a floored fraction of the zoomed-out pan
    And zooming in 5 notches shrank the camera distance by at least a third
