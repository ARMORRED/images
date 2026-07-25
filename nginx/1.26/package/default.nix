{
  callPackage,
  withHardening ? false,
  withExtraHardening ? false,
  ...
}@args:

callPackage ./generic.nix (args // { inherit withHardening withExtraHardening; }) {
  version = "1.26.3";
  hash = "sha256-ae4rI3dEA25h0kuDZmiq0wQN2kYf5vVw8Xh+q1cMdao=";
}
