Feature: Settlement labels
  Labels are sized by settlement type (towns largest, villages smallest) and drawn
  as plain text with no outline and no filled dark box, so nothing looks highlighted
  and the terrain still shows through between the glyphs.

  Background:
    Given the studio is loaded with the campaign scene

  Scenario: Label size scales with settlement type
    Then the town label is larger than the castle label
    And the castle label is larger than the village label
    And the town label is at least 1.6 times the village label

  Scenario: Labels are plain text with no dark box
    Then the label glyphs are bright and legible
    And terrain shows through the label area instead of a dark slab
