Feature: Settlement placement
  Movable settlement markers are coloured by how much of their footprint zone sits
  on land (rivers and lakes count as water via the navmesh oracle). Reference
  settlements are locked. Markers can be dragged to stage a move, and each
  settlement type has a distinct marker shape.

  Background:
    Given the studio is loaded with the campaign scene

  Scenario: Marker colour matches each settlement's land verdict
    Then every movable marker colour matches its land fraction
    And reference settlements are the locked grey colour and are not movable

  Scenario: The map mixes land, coastal and water settlements
    Then there are movable markers fully on land
    And there are movable markers partly on land
    And there are movable markers fully in water
    And the info line reports a part-land count
    And the legend includes the amber "partly on land" row

  Scenario: Dragging a movable marker stages a move
    When I drag an on-screen movable land marker across the map
    Then the moved counter increments
    And the save-placements button shows the pending count

  Scenario: A reference settlement cannot be dragged
    When I try to drag an on-screen reference marker
    Then no move is staged

  Scenario: Markers use a distinct shape per settlement type
    Then the markers include cones, cylinders and spheres
    And movable settlements with a radius have a footprint ring
