using System.Windows;
using System.Windows.Media;

namespace Dannify.Setup.UI
{
    /// <summary>
    /// The Dannify mark, drawn from the same shapes as frontend/src/assets/dannify.svg:
    /// a green tile, and a D whose counter is a play triangle. Built as
    /// vectors so it is sharp at any display scale.
    /// </summary>
    internal static class Logo
    {
        private static Color C(string hex) => (Color)ColorConverter.ConvertFromString(hex);

        public static DrawingImage Build()
        {
            var tileShape = new RectangleGeometry(new Rect(12, 12, 232, 232), 54, 54);

            var tile = new LinearGradientBrush { StartPoint = new Point(0.08, 0), EndPoint = new Point(0.92, 1) };
            tile.GradientStops.Add(new GradientStop(C("#FF3DF58A"), 0));
            tile.GradientStops.Add(new GradientStop(C("#FF17C95E"), 0.52));
            tile.GradientStops.Add(new GradientStop(C("#FF05823A"), 1));

            var sheen = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(0.35, 1) };
            sheen.GradientStops.Add(new GradientStop(Color.FromArgb(77, 255, 255, 255), 0));
            sheen.GradientStops.Add(new GradientStop(Color.FromArgb(0, 255, 255, 255), 0.55));

            // The D, with a play triangle cut out of it. The SVG rounds the
            // triangle's corners with a 9 px round-joined stroke in the mask;
            // widening the triangle by the same pen does the same here.
            var d = Geometry.Parse("M67,62 H123 A66,66 0 0 1 123,194 H67 Z");
            var triangle = Geometry.Parse("M104,98 L104,158 L154,128 Z");
            var widened = triangle.GetWidenedPathGeometry(new Pen(Brushes.Black, 9) { LineJoin = PenLineJoin.Round });
            var counter = Geometry.Combine(triangle, widened, GeometryCombineMode.Union, null);
            var mark = Geometry.Combine(d, counter, GeometryCombineMode.Exclude, null);

            var markFill = new LinearGradientBrush { StartPoint = new Point(0.1, 0), EndPoint = new Point(0.55, 1) };
            markFill.GradientStops.Add(new GradientStop(C("#FFFFFFFF"), 0));
            markFill.GradientStops.Add(new GradientStop(C("#FFDFFCEB"), 1));

            var drop = mark.Clone();
            drop.Transform = new TranslateTransform(0, 6);

            var all = new DrawingGroup();
            all.Children.Add(new GeometryDrawing(Brushes.Transparent, null, new RectangleGeometry(new Rect(0, 0, 256, 256))));
            all.Children.Add(new GeometryDrawing(tile, null, tileShape));

            var inside = new DrawingGroup { ClipGeometry = tileShape };
            inside.Children.Add(new GeometryDrawing(sheen, null, new EllipseGeometry(new Point(62, 10), 150, 120)));
            var shadow = new DrawingGroup { Opacity = 0.28 };
            shadow.Children.Add(new GeometryDrawing(new SolidColorBrush(C("#FF00351A")), null, drop));
            inside.Children.Add(shadow);
            all.Children.Add(inside);

            all.Children.Add(new GeometryDrawing(markFill, null, mark));
            all.Children.Add(new GeometryDrawing(null,
                new Pen(new SolidColorBrush(Color.FromArgb(56, 255, 255, 255)), 1.5),
                new RectangleGeometry(new Rect(12.75, 12.75, 230.5, 230.5), 53.25, 53.25)));

            all.Freeze();
            var image = new DrawingImage(all);
            image.Freeze();
            return image;
        }
    }
}
